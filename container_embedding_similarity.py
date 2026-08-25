"""
retest_data 폴더의 용기 사진들(락앤락/생수병/원형용기)을 DINOv2로 임베딩(특징 벡터)을
뽑아서, 같은 용기 사진끼리의 평균 코사인 유사도와 서로 다른 용기 사진 간의 평균 코사인
유사도를 비교한다.

1) rembg로 배경을 제거한 크롭 버전(cropped_dataset)을 자동 생성
2) 원본(retest_data) vs 크롭(cropped_dataset) 각각에 대해 DINOv2로 동일 실험을 수행
3) 두 결과(원본×DINOv2, 크롭×DINOv2)를 한 표/그래프로 비교
"""
import itertools
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import transforms

DATA_DIR = Path(r"C:\Users\PKNU-ICEE\Desktop\project\retest_data")
CROPPED_DIR = Path(r"C:\Users\PKNU-ICEE\Desktop\project\cropped_dataset")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def find_class_folders(root: Path):
    # "container_dataset 락앤락" 같은 폴더 이름에서 뒤쪽 라벨만 사용
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    return {p.name.split(" ")[-1]: p for p in folders}


def remove_background(src_dir: Path, dst_dir: Path):
    """src_dir의 클래스별 폴더 사진들의 배경을 rembg로 제거해 dst_dir에 동일 폴더 구조로 저장.
    이미 처리되어 있는 파일은 다시 처리하지 않는다(재실행 시 이어서 처리)."""
    from rembg import new_session, remove

    session = new_session("u2net")
    class_folders = find_class_folders(src_dir)
    for label, folder in class_folders.items():
        out_folder = dst_dir / folder.name
        out_folder.mkdir(parents=True, exist_ok=True)
        paths = sorted(folder.glob("*.jpg"))
        n_done = 0
        for p in paths:
            out_path = out_folder / p.name
            if out_path.exists():
                continue
            img = Image.open(p).convert("RGB")
            cutout = remove(img, session=session)  # RGBA, 배경 투명
            # 임베딩 모델 입력은 3채널이 필요하므로 흰 배경 위에 합성 후 JPG로 저장
            canvas = Image.new("RGB", cutout.size, (255, 255, 255))
            canvas.paste(cutout, mask=cutout.split()[3])
            canvas.save(out_path, "JPEG", quality=95)
            n_done += 1
        print(f"[배경 제거] {label}: 신규 {n_done}장 처리 (총 {len(paths)}장) -> {out_folder}")


def load_dinov2():
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14")
    model.eval().to(DEVICE)
    preprocess = transforms.Compose([
        transforms.Resize(256, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    return model, preprocess


@torch.no_grad()
def extract_embeddings(model, preprocess, image_paths, batch_size=16):
    feats = []
    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i + batch_size]
        imgs = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in batch_paths])
        out = model(imgs.to(DEVICE))
        feats.append(out.cpu().numpy())
    return np.concatenate(feats, axis=0)


def cosine_sim_matrix(a, b):
    a_n = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_n = b / np.linalg.norm(b, axis=1, keepdims=True)
    return a_n @ b_n.T


def mean_within(sim):
    n = sim.shape[0]
    mask = ~np.eye(n, dtype=bool)
    return sim[mask].mean()


def compute_similarity(model, preprocess, class_folders):
    embeddings = {}
    for label, folder in class_folders.items():
        paths = sorted(folder.glob("*.jpg"))
        print(f"[{label}] {len(paths)}장 임베딩 추출 중...")
        embeddings[label] = extract_embeddings(model, preprocess, paths)

    labels = list(embeddings.keys())

    within = {label: mean_within(cosine_sim_matrix(embeddings[label], embeddings[label]))
              for label in labels}
    between = {(a, b): cosine_sim_matrix(embeddings[a], embeddings[b]).mean()
               for a, b in itertools.combinations(labels, 2)}
    overall_within = float(np.mean(list(within.values())))
    overall_between = float(np.mean(list(between.values())))
    return labels, within, between, overall_within, overall_between


def print_result(title, within, between, overall_within, overall_between):
    print(f"\n=== {title}: 같은 용기끼리 평균 코사인 유사도 (클래스 내부) ===")
    for label, v in within.items():
        print(f"  {label:10s}: {v:.4f}")
    print(f"  {'전체 평균':10s}: {overall_within:.4f}")

    print(f"\n=== {title}: 서로 다른 용기 간 평균 코사인 유사도 (클래스 간) ===")
    for (a, b), v in between.items():
        print(f"  {a} vs {b:10s}: {v:.4f}")
    print(f"  {'전체 평균':10s}: {overall_between:.4f}")

    print(f"\n{title} 요약: 클래스 내부 {overall_within:.4f}  vs  클래스 간 {overall_between:.4f}"
          f"  (차이 {overall_within - overall_between:+.4f})")


def main():
    remove_background(DATA_DIR, CROPPED_DIR)

    model, preprocess = load_dinov2()

    orig_folders = find_class_folders(DATA_DIR)
    crop_folders = find_class_folders(CROPPED_DIR)

    orig = compute_similarity(model, preprocess, orig_folders)
    print_result("원본×DINOv2", orig[1], orig[2], orig[3], orig[4])

    crop = compute_similarity(model, preprocess, crop_folders)
    print_result("크롭×DINOv2", crop[1], crop[2], crop[3], crop[4])

    save_comparison(orig, crop)


def save_comparison(orig, crop):
    import csv

    _, orig_within, orig_between, orig_ow, orig_ob = orig
    _, crop_within, crop_between, crop_ow, crop_ob = crop

    out_dir = DATA_DIR.parent
    csv_path = out_dir / "similarity_result_compare.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["구성", "클래스", "클래스 내부 평균", "클래스 간 평균(해당 클래스 관여)"])
        for label in orig_within:
            w.writerow(["원본×DINOv2", label, f"{orig_within[label]:.4f}", ""])
        w.writerow(["원본×DINOv2", "전체 평균", f"{orig_ow:.4f}", f"{orig_ob:.4f}"])
        for label in crop_within:
            w.writerow(["크롭×DINOv2", label, f"{crop_within[label]:.4f}", ""])
        w.writerow(["크롭×DINOv2", "전체 평균", f"{crop_ow:.4f}", f"{crop_ob:.4f}"])
        w.writerow([])
        w.writerow(["구성", "클래스 내부 평균", "클래스 간 평균", "차이(구분력)"])
        w.writerow(["원본×DINOv2", f"{orig_ow:.4f}", f"{orig_ob:.4f}", f"{orig_ow - orig_ob:+.4f}"])
        w.writerow(["크롭×DINOv2", f"{crop_ow:.4f}", f"{crop_ob:.4f}", f"{crop_ow - crop_ob:+.4f}"])
    print(f"\n비교표 저장: {csv_path}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False

    configs = ["원본×DINOv2", "크롭×DINOv2"]
    within_vals = [orig_ow, crop_ow]
    between_vals = [orig_ob, crop_ob]
    diff_vals = [orig_ow - orig_ob, crop_ow - crop_ob]

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    x = np.arange(len(configs))
    width = 0.35
    axes[0].bar(x - width / 2, within_vals, width, label="같은 용기(클래스 내부)", color="#4c8bf5")
    axes[0].bar(x + width / 2, between_vals, width, label="다른 용기(클래스 간)", color="#f5734c")
    axes[0].set_xticks(x); axes[0].set_xticklabels(configs)
    axes[0].set_ylim(0, 1)
    axes[0].set_title("원본 vs 크롭 — 클래스 내부/간 유사도")
    axes[0].legend()
    for xi, v in zip(x - width / 2, within_vals):
        axes[0].text(xi, v + 0.02, f"{v:.4f}", ha="center", fontsize=9)
    for xi, v in zip(x + width / 2, between_vals):
        axes[0].text(xi, v + 0.02, f"{v:.4f}", ha="center", fontsize=9)

    axes[1].bar(configs, diff_vals, color=["#4c8bf5", "#2ca02c"])
    axes[1].set_title("구분력 (클래스 내부 - 클래스 간)")
    for xi, v in enumerate(diff_vals):
        axes[1].text(xi, v + 0.005, f"{v:+.4f}", ha="center")

    fig.tight_layout()
    png_path = out_dir / "similarity_result_compare.png"
    fig.savefig(png_path, dpi=150)
    print(f"비교 그래프 저장: {png_path}")


if __name__ == "__main__":
    main()
