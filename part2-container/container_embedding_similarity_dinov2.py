"""
retest_data 폴더의 용기 사진들(락앤락/생수병/원형용기)을 DINOv2(ViT-S/14)로
임베딩(특징 벡터)을 뽑아서, 같은 용기 사진끼리의 평균 코사인 유사도와
서로 다른 용기 사진 간의 평균 코사인 유사도를 비교한다.

container_embedding_similarity.py(ResNet50 버전)와 비교하기 위한 스크립트.
"""
import itertools
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import transforms

DATA_DIR = Path(r"C:\Users\PKNU-ICEE\Desktop\project\retest_data")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def find_class_folders(root: Path):
    # "container_dataset 락앤락" 같은 폴더 이름에서 뒤쪽 라벨만 사용
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    return {p.name.split(" ")[-1]: p for p in folders}


def load_model():
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


def main():
    class_folders = find_class_folders(DATA_DIR)
    print("발견한 클래스:", list(class_folders.keys()))

    model, preprocess = load_model()

    embeddings = {}
    for label, folder in class_folders.items():
        paths = sorted(folder.glob("*.jpg"))
        print(f"[{label}] {len(paths)}장 임베딩 추출 중...")
        embeddings[label] = extract_embeddings(model, preprocess, paths)

    labels = list(embeddings.keys())

    within = {}
    for label in labels:
        sim = cosine_sim_matrix(embeddings[label], embeddings[label])
        within[label] = mean_within(sim)

    between = {}
    for a, b in itertools.combinations(labels, 2):
        sim = cosine_sim_matrix(embeddings[a], embeddings[b])
        between[(a, b)] = sim.mean()

    print("\n=== 같은 용기끼리 평균 코사인 유사도 (클래스 내부) ===")
    for label, v in within.items():
        print(f"  {label:10s}: {v:.4f}")
    overall_within = np.mean(list(within.values()))
    print(f"  {'전체 평균':10s}: {overall_within:.4f}")

    print("\n=== 서로 다른 용기 간 평균 코사인 유사도 (클래스 간) ===")
    for (a, b), v in between.items():
        print(f"  {a} vs {b:10s}: {v:.4f}")
    overall_between = np.mean(list(between.values()))
    print(f"  {'전체 평균':10s}: {overall_between:.4f}")

    print(f"\n요약: 클래스 내부 평균 {overall_within:.4f}  vs  클래스 간 평균 {overall_between:.4f}"
          f"  (차이 {overall_within - overall_between:+.4f})")

    save_outputs(labels, embeddings, within, between, overall_within, overall_between)


def save_outputs(labels, embeddings, within, between, overall_within, overall_between):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    import csv

    out_dir = DATA_DIR.parent
    csv_path = out_dir / "similarity_result_dinov2.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["구분", "대상", "평균 코사인 유사도"])
        for label, v in within.items():
            w.writerow(["클래스 내부", label, f"{v:.4f}"])
        w.writerow(["클래스 내부", "전체 평균", f"{overall_within:.4f}"])
        for (a, b), v in between.items():
            w.writerow(["클래스 간", f"{a} vs {b}", f"{v:.4f}"])
        w.writerow(["클래스 간", "전체 평균", f"{overall_between:.4f}"])
    print(f"\n표 저장: {csv_path}")

    n = len(labels)
    mat = np.zeros((n, n))
    for i, a in enumerate(labels):
        for j, b in enumerate(labels):
            if i == j:
                mat[i, j] = within[a]
            else:
                key = (a, b) if (a, b) in between else (b, a)
                mat[i, j] = between[key]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    im = axes[0].imshow(mat, vmin=0, vmax=1, cmap="viridis")
    axes[0].set_xticks(range(n)); axes[0].set_xticklabels(labels)
    axes[0].set_yticks(range(n)); axes[0].set_yticklabels(labels)
    axes[0].set_title("클래스 쌍별 평균 코사인 유사도 (DINOv2)")
    for i in range(n):
        for j in range(n):
            axes[0].text(j, i, f"{mat[i, j]:.3f}", ha="center", va="center", color="white")
    fig.colorbar(im, ax=axes[0], fraction=0.046)

    axes[1].bar(["같은 용기\n(클래스 내부)", "다른 용기\n(클래스 간)"],
                [overall_within, overall_between], color=["#4c8bf5", "#f5734c"])
    axes[1].set_ylim(0, 1)
    axes[1].set_title("전체 평균 비교 (DINOv2)")
    for x, v in enumerate([overall_within, overall_between]):
        axes[1].text(x, v + 0.02, f"{v:.4f}", ha="center")

    fig.tight_layout()
    png_path = DATA_DIR.parent / "similarity_result_dinov2.png"
    fig.savefig(png_path, dpi=150)
    print(f"그래프 저장: {png_path}")


if __name__ == "__main__":
    main()
