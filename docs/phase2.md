# Phase2: カメラ搭載

## Goal

Raspberry Pi 5へカメラを搭載し、Pythonから静止画と映像を取得する。
最初は撮影を安定させ、その後にOpenCVによる色・人物認識へ進む。

## Recommended Build

- Raspberry Pi Camera Module 3 Wide（通常光モデル）
- Raspberry Pi 5用 Standard–Miniカメラケーブル（15ピン→22ピン）
- カメラ固定用ブラケットまたはスペーサー

Wide版は視野角が広く、走行中に前方を捉えやすい。暗視を使わない段階では、色が自然な通常光モデルを選ぶ。

## Step 1: 接続

1. Raspberry Piをシャットダウンする。
2. USB-C電源とモーター用電池を外す。
3. Pi 5の`CAM/DISP0`または`CAM/DISP1`へ、Standard–Miniケーブルの22ピン側を挿す。
4. カメラへ15ピン側を挿す。
5. ケーブルが斜めになっていないことを確認してロックする。

端子の接点面は、コネクタの可動フラップとは反対側へ向ける。通電中に抜き差ししない。

## Step 2: OSから認識確認

Raspberry Pi上で実行する。

```sh
rpicam-hello --list-cameras
```

Camera Module 3なら、通常は`imx708`が表示される。

静止画を直接撮影する。

```sh
mkdir -p captures
rpicam-still -o captures/rpicam-test.jpg
```

## Step 3: Picamera2を確認

Raspberry Pi OSの標準パッケージを使用する。

```sh
sudo apt update
sudo apt install -y python3-picamera2 --no-install-recommends
```

Buddyの撮影CLIを実行する。

```sh
python3 -m robot.camera_cli \
  --backend picamera2 \
  --output captures/latest.jpg
```

撮影画像をMacへコピーする例:

```sh
scp pi@buddy.local:~/buddy/captures/latest.jpg .
```

## Step 4: 車体へ固定

- レンズを車体前方へ向ける。
- タイヤや床が画面の大部分を占めない高さにする。
- リボンケーブルを鋭角に折らない。
- ケーブルがタイヤ、モーター、ファンに接触しないよう固定する。
- カメラ基板の裏面が金属や裸の端子へ触れないようにする。

## Phase2 Checklist

- [ ] Camera Module 3 WideとPi 5用ケーブルを用意
- [ ] 電源OFFでカメラを接続
- [ ] `rpicam-hello --list-cameras`で認識
- [ ] `rpicam-still`で静止画撮影
- [ ] `robot.camera_cli`で静止画撮影
- [ ] 車体へカメラを固定
- [ ] 走行中の映像取得
- [ ] OpenCVで色認識
