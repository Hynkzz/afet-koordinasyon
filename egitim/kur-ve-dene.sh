#!/bin/bash
# Afet projesi YOLO egitim ortami: ComfyUI venvinden ayri. Kurulum + kucuk deneme egitimi.
set -e
# /tmp 7 GB tmpfs; ROCm torch paketi acilirken sigmiyor.
export TMPDIR=~/.cache/piptmp
cd ~/afet-yolo
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q torch torchvision --index-url https://download.pytorch.org/whl/rocm7.2
venv/bin/pip install -q ultralytics
# Sunucu minimal, libGL yok ve sudo yok; ekransiz opencv yeterli.
venv/bin/pip uninstall -y -q opencv-python
venv/bin/pip install -q --force-reinstall --no-deps opencv-python-headless
venv/bin/python -c "import torch,ultralytics;print(\"torch\",torch.__version__,\"gpu\",torch.cuda.is_available(),torch.cuda.get_device_name(0));print(\"ultralytics\",ultralytics.__version__)"
# coco8: 8 resimlik ornek veri, sadece GPU ile egitimin calistigini dogrulamak icin
SECONDS=0
venv/bin/yolo detect train model=yolo11n.pt data=coco8.yaml epochs=10 imgsz=640 batch=8 device=0 project=denemeler name=coco8 exist_ok=True
echo "egitim suresi $SECONDS sn"
venv/bin/yolo detect val model=runs/detect/denemeler/coco8/weights/best.pt data=coco8.yaml device=0
echo BITTI
