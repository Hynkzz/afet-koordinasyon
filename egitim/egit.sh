#!/bin/bash
# C2A ile YOLO11n ince ayari. Once hazir modelin olcumu, sonra egitim, sonra test kumesinde olcum.
set -e
export TMPDIR=~/.cache/piptmp
cd ~/afet-yolo
[ -d veri/new_dataset3 ] || venv/bin/python -c "import zipfile; zipfile.ZipFile(\"veri/c2a.zip\").extractall(\"veri\")"
echo "== hazir model (COCO), C2A test"
venv/bin/yolo detect val model=yolo11n.pt data=c2a.yaml split=test classes=0 imgsz=640 batch=32 device=0 project=sonuclar name=hazir-test exist_ok=True
echo "== egitim"
SECONDS=0
venv/bin/yolo detect train model=yolo11n.pt data=c2a.yaml epochs=60 patience=15 imgsz=640 batch=32 workers=8 device=0 project=sonuclar name=c2a-yolo11n exist_ok=True
echo "egitim suresi $SECONDS sn"
echo "== egitilmis model, C2A test"
venv/bin/yolo detect val model=runs/detect/sonuclar/c2a-yolo11n/weights/best.pt data=c2a.yaml split=test imgsz=640 batch=32 device=0 project=sonuclar name=egitilmis-test exist_ok=True
echo BITTI
