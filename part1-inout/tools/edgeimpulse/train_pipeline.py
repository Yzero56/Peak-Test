#!/usr/bin/env python3
"""
train_pipeline.py — data/raw_captures/*.jpg를 Edge Impulse에 올려서
비전 분류 모델을 학습시키는 파이프라인.

.claude/skills/xiao-edgeimpulse-train/SKILL.md에 정리된 REST API 순서를
그대로 따른다 (PowerShell curl.exe 대신 requests로 옮긴 버전). 파일명 규칙은
tools/capture_image.py, tools/web_capture/ 와 동일한
"<label>_<timestamp>_<idx>.jpg" 를 그대로 라벨 소스로 쓴다.

사용법:
  ./.venv/bin/python tools/edgeimpulse/train_pipeline.py status
  ./.venv/bin/python tools/edgeimpulse/train_pipeline.py upload
  ./.venv/bin/python tools/edgeimpulse/train_pipeline.py train
  ./.venv/bin/python tools/edgeimpulse/train_pipeline.py deploy
  ./.venv/bin/python tools/edgeimpulse/train_pipeline.py all
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "data" / "raw_captures"
BUILD_DIR = ROOT / "build"

FNAME_RE = re.compile(r"^(?P<label>.+)_(?P<ts>\d+)_(?P<idx>\d{3})\.jpg$")
API = "https://studio.edgeimpulse.com/v1/api"
INGESTION = "https://ingestion.edgeimpulse.com/api/training/files"

IMAGE_SIZE = 96
TRAIN_CYCLES = 20
LEARNING_RATE = 0.0005


def load_api_key(key_env: str = "EI_API_KEY") -> str:
    """.env에서 API 키를 읽는다. 프로젝트가 여러 개면(예: 용기 인식용 EI_API_KEY와
    IN/OUT용 별도 프로젝트) --key-env로 다른 변수명을 지정해서 서로 안 섞이게 한다."""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{key_env}="):
                return line.split("=", 1)[1].strip()
    sys.exit(f".env에 {key_env}가 없습니다.")


def state_file_for(key_env: str) -> Path:
    """키 변수마다 별도 state 파일을 써서 업로드 기록/project_id 캐시가 프로젝트
    간에 섞이지 않게 한다 (기존 EI_API_KEY는 예전 파일명 그대로 하위호환)."""
    if key_env == "EI_API_KEY":
        return ROOT / "data" / "edgeimpulse_state.json"
    return ROOT / "data" / f"edgeimpulse_state_{key_env.lower()}.json"


def load_state(key_env: str) -> dict:
    path = state_file_for(key_env)
    if path.exists():
        return json.loads(path.read_text())
    return {"uploaded": [], "project_id": None}


def save_state(state: dict, key_env: str):
    state_file_for(key_env).write_text(json.dumps(state, indent=2, ensure_ascii=False))


def get_project_id(key: str, state: dict, key_env: str) -> int:
    if state.get("project_id"):
        return state["project_id"]
    r = requests.get(f"{API}/projects", headers={"x-api-key": key})
    r.raise_for_status()
    projects = r.json()["projects"]
    if not projects:
        sys.exit("Edge Impulse 프로젝트가 없습니다.")
    proj_id = projects[0]["id"]
    state["project_id"] = proj_id
    save_state(state, key_env)
    return proj_id


def local_dataset(labels_filter: set | None = None):
    """data/raw_captures의 파일명에서 라벨을 뽑아 {label: [Path, ...]} 로 묶는다.
    labels_filter를 주면 그 라벨들만(예: in/out/hand_only/holding + pair 변형) —
    같은 폴더에 다른 작업용 라벨(예: 용기 인식 egg/ham/soymilk)이 섞여있어도
    엉뚱한 프로젝트로 안 올라가게."""
    by_label = {}
    for f in sorted(CAPTURE_DIR.glob("*.jpg")):
        m = FNAME_RE.match(f.name)
        if not m:
            continue
        label = m.group("label")
        if labels_filter is not None and label not in labels_filter:
            continue
        by_label.setdefault(label, []).append(f)
    return by_label


def parse_labels_arg(args) -> set | None:
    if not getattr(args, "labels", None):
        return None
    return {s.strip() for s in args.labels.split(",") if s.strip()}


def cmd_status(args):
    by_label = local_dataset(parse_labels_arg(args))
    if not by_label:
        print("data/raw_captures에 라벨 붙은 사진이 없습니다.")
        return
    print("로컬 데이터셋:")
    total = 0
    for label, files in sorted(by_label.items(), key=lambda kv: -len(kv[1])):
        print(f"  {label:24s} {len(files):3d}장")
        total += len(files)
    print(f"  {'합계':24s} {total:3d}장  ({len(by_label)}개 클래스)")
    if any(len(f) < 15 for f in by_label.values()):
        print("\n  ⚠ 15장 미만인 클래스가 있습니다 — 학습 품질이 떨어질 수 있어요.")
    if len(by_label) < 2:
        print("\n  ⚠ 클래스가 1개뿐이면 분류 학습이 의미가 없습니다 (최소 2개, 배경 클래스 포함 권장).")


def cmd_upload(args):
    key = load_api_key(args.key_env)
    state = load_state(args.key_env)
    proj = get_project_id(key, state, args.key_env)
    by_label = local_dataset(parse_labels_arg(args))
    uploaded = set(state.get("uploaded", []))

    to_upload = [(label, f) for label, files in by_label.items() for f in files if f.name not in uploaded]
    if not to_upload:
        print("새로 올릴 사진이 없습니다 (이미 다 업로드됨).")
        return

    print(f"{len(to_upload)}장 업로드 중 (project {proj})...")
    ok, fail = 0, 0
    for label, f in to_upload:
        with open(f, "rb") as fh:
            r = requests.post(
                INGESTION,
                headers={"x-api-key": key, "x-label": label},
                files={"data": (f.name, fh, "image/jpeg")},
            )
        if r.status_code == 200 and r.json().get("success"):
            uploaded.add(f.name)
            ok += 1
            # 파일마다 바로 저장 — 220장쯤 올리는 데 몇 분씩 걸리다 보니 중간에
            # 타임아웃/중단되면 끝에서만 저장하는 방식은 진행 상황을 통째로 잃어버려서
            # 재실행할 때 이미 올라간 사진을 중복으로 다시 올리는 사고가 실제로 났었다.
            state["uploaded"] = sorted(uploaded)
            save_state(state, args.key_env)
        else:
            print(f"  FAIL {f.name}: {r.status_code} {r.text[:200]}")
            fail += 1
    print(f"완료: {ok}장 성공, {fail}장 실패")

    if ok:
        r = requests.post(f"{API}/{proj}/rebalance", headers={"x-api-key": key})
        print("rebalance:", "OK" if r.ok and r.json().get("success") else r.text[:200])


def poll_job(key: str, proj: int, job_id: int, label: str, timeout_s: int = 900):
    print(f"  [{label}] job {job_id} 폴링 중...", end="", flush=True)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = requests.get(f"{API}/{proj}/jobs/{job_id}/status", headers={"x-api-key": key})
        r.raise_for_status()
        job = r.json().get("job", {})
        if job.get("finished"):
            ok = job.get("finishedSuccessful")
            print(" 끝" if ok else " 실패")
            if not ok:
                logs = requests.get(f"{API}/{proj}/jobs/{job_id}/stdout", headers={"x-api-key": key})
                lines = logs.json().get("stdout", [])[:20]
                for line in lines:
                    print("   ", line.get("data", ""))
            return ok
        print(".", end="", flush=True)
        time.sleep(8)
    print(" 타임아웃")
    return False


def cmd_train(args):
    key = load_api_key(args.key_env)
    state = load_state(args.key_env)
    proj = get_project_id(key, state, args.key_env)
    headers = {"x-api-key": key, "Content-Type": "application/json"}

    by_label = local_dataset(parse_labels_arg(args))
    if len(by_label) < 2:
        sys.exit("클래스가 2개 이상 필요합니다 (지금은 status로 확인해보세요).")

    print("임펄스 생성...")
    impulse_body = {
        "inputBlocks": [{
            "id": 1, "type": "image", "name": "Images", "title": "Image data",
            "imageWidth": IMAGE_SIZE, "imageHeight": IMAGE_SIZE, "resizeMode": "squash",
        }],
        "dspBlocks": [{
            "id": 2, "type": "image", "name": "Image", "axes": ["image"],
            "title": "Image", "implementationVersion": 1,
        }],
        "learnBlocks": [{
            "id": 3, "type": "keras-transfer-image", "name": "Transfer learning",
            "dsp": [2], "title": "Transfer learning (Images)",
        }],
    }
    r = requests.post(f"{API}/{proj}/impulse", headers=headers, json=impulse_body)
    print("  ", r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200])

    print("피처 생성...")
    r = requests.post(f"{API}/{proj}/jobs/generate-features", headers=headers,
                       json={"dspId": 2, "calculateFeatureImportance": False})
    r.raise_for_status()
    job_id = r.json()["id"]
    if not poll_job(key, proj, job_id, "generate-features"):
        sys.exit("피처 생성 실패")

    print("학습 시작...")
    r = requests.post(f"{API}/{proj}/jobs/train/keras/3", headers=headers,
                       json={"trainingCycles": TRAIN_CYCLES, "learningRate": LEARNING_RATE})
    r.raise_for_status()
    job_id = r.json()["id"]
    ok = poll_job(key, proj, job_id, "train", timeout_s=1200)

    logs = requests.get(f"{API}/{proj}/jobs/{job_id}/stdout", headers={"x-api-key": key})
    lines = [l.get("data", "") for l in logs.json().get("stdout", [])]
    acc_lines = [l for l in lines if "val_accuracy" in l or "accuracy" in l.lower()]
    print("\n--- 정확도 관련 로그 (최근 순) ---")
    for l in acc_lines[:15]:
        print(" ", l)

    if not ok:
        sys.exit("학습 실패")
    print("\n학습 완료. Edge Impulse Studio에서 자세한 confusion matrix 확인 가능:")
    print(f"  https://studio.edgeimpulse.com/studio/{proj}/learning/keras")


def cmd_deploy(args):
    key = load_api_key(args.key_env)
    state = load_state(args.key_env)
    proj = get_project_id(key, state, args.key_env)
    headers = {"x-api-key": key, "Content-Type": "application/json"}

    print("아두이노 라이브러리 빌드...")
    r = requests.post(f"{API}/{proj}/jobs/build-ondevice-model", headers=headers,
                       params={"type": "arduino"}, json={"engine": "tflite-eon"})
    r.raise_for_status()
    job_id = r.json()["id"]
    if not poll_job(key, proj, job_id, "build-arduino", timeout_s=600):
        sys.exit("빌드 실패")

    print("라이브러리 다운로드...")
    r = requests.get(f"{API}/{proj}/deployment/download", headers={"x-api-key": key},
                      params={"type": "arduino"})
    r.raise_for_status()
    BUILD_DIR.mkdir(exist_ok=True)
    out = BUILD_DIR / f"{args.key_env.lower()}_inferencing.zip"
    out.write_bytes(r.content)
    print(f"저장됨: {out} ({len(r.content)} bytes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-env", default="EI_API_KEY",
                     help=".env에서 읽을 API 키 변수명 — 프로젝트가 여러 개면 서로 다른 값 지정 "
                          "(예: 용기 인식은 EI_API_KEY, IN/OUT은 EI_API_KEY_INOUT)")
    ap.add_argument("--labels", default=None,
                     help="이 프로젝트에 올릴 라벨만 콤마로 지정 (예: in,out,hand_only,holding,in-pair,out-pair). "
                          "생략하면 data/raw_captures에 있는 라벨을 전부 대상으로 함 — 다른 작업용 라벨과 "
                          "섞여있으면 반드시 지정할 것.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("upload")
    sub.add_parser("train")
    sub.add_parser("deploy")
    sub.add_parser("all")
    args = ap.parse_args()

    if args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "upload":
        cmd_upload(args)
    elif args.cmd == "train":
        cmd_train(args)
    elif args.cmd == "deploy":
        cmd_deploy(args)
    elif args.cmd == "all":
        cmd_status(args)
        cmd_upload(args)
        cmd_train(args)
        cmd_deploy(args)


if __name__ == "__main__":
    main()
