#!/bin/bash
# Karisik veriyle ince ayar; sonra iki test kumesinde de olcum.
set -e
export TMPDIR=~/.cache/piptmp
cd ~/afet-yolo
until [ -f veri/coco/bitti ]; do sleep 10; done
venv/bin/python karisik_hazirla.py
SECONDS=0
venv/bin/yolo detect train model=yolo11n.pt data=karisik.yaml epochs=60 patience=15 imgsz=640 batch=32 workers=8 device=0 project=sonuclar name=karisik-yolo11n exist_ok=True
echo "egitim suresi $SECONDS sn"
echo "== karisik model, C2A test"
venv/bin/yolo detect val model=runs/detect/sonuclar/karisik-yolo11n/weights/best.pt data=c2a.yaml split=test imgsz=640 batch=32 device=0 project=sonuclar name=karisik-c2a-test exist_ok=True
echo "== karisik model, coco128 insan"
venv/bin/yolo detect val model=runs/detect/sonuclar/karisik-yolo11n/weights/best.pt data=coco128.yaml classes=0 imgsz=640 batch=32 device=0 project=sonuclar name=karisik-coco128 exist_ok=True
echo BITTI
