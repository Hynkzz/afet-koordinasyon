#!/bin/bash
# MOT17 eklenmis karisik veriyle ince ayar; sonra C2A test ve coco128 olcumu (MOT20 laptopta).
set -e
export TMPDIR=~/.cache/piptmp
cd ~/afet-yolo
mkdir -p veri/mot17 && cd veri/mot17
[ -f MOT17.zip ] || curl -sSL -o MOT17.zip https://motchallenge.net/data/MOT17.zip
[ -d MOT17/train ] || ../../venv/bin/python -c "import zipfile; z=zipfile.ZipFile('MOT17.zip'); z.extractall('.', [n for n in z.namelist() if n.startswith('MOT17/train/') and '-FRCNN/' in n])"
cd ~/afet-yolo
venv/bin/python mot_hazirla.py --mot veri/mot17/MOT17/train --cikti veri/mot17-yolo --adim 5
venv/bin/python karisik2_hazirla.py
SECONDS=0
venv/bin/yolo detect train model=yolo11n.pt data=karisik2.yaml epochs=60 patience=15 imgsz=640 batch=32 workers=8 device=0 project=sonuclar name=karisik2-yolo11n exist_ok=True
echo "egitim suresi $SECONDS sn"
echo "== karisik2 model, C2A test"
venv/bin/yolo detect val model=runs/detect/sonuclar/karisik2-yolo11n/weights/best.pt data=c2a.yaml split=test imgsz=640 batch=32 device=0 project=sonuclar name=karisik2-c2a-test exist_ok=True
echo "== karisik2 model, coco128 insan"
venv/bin/yolo detect val model=runs/detect/sonuclar/karisik2-yolo11n/weights/best.pt data=coco128.yaml classes=0 imgsz=640 batch=32 device=0 project=sonuclar name=karisik2-coco128 exist_ok=True
echo BITTI
