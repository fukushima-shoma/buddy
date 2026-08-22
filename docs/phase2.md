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

## Step 5: OpenCVで色を検出

Raspberry Pi OSのパッケージからOpenCVを導入する。

```sh
sudo apt update
sudo apt install -y python3-opencv opencv-data
```

赤い物体を含む静止画を撮影する。

```sh
python3 -m robot.camera_cli \
  --backend picamera2 \
  --output captures/latest.jpg
```

画像内で最も大きな赤い領域を検出する。

```sh
python3 -m robot.color_cli \
  --input captures/latest.jpg \
  --color red \
  --output captures/color-detected.jpg
```

`detected=true`なら、物体の位置が`left`、`center`、`right`のいずれかで表示される。緑と青は`--color green`または`--color blue`で試せる。

## Step 6: リアルタイム色認識

モーターを動かさず、15秒間だけカメラ映像内の赤い物体を追跡する。

```sh
python3 -m robot.live_color_cli --color red
```

端末には`left`、`center`、`right`、`not-found`が表示される。最後に処理したフレームは`captures/live-color.jpg`へ保存される。

物体をカメラの左右へゆっくり動かし、位置表示が変わることを確認する。途中で止める場合は`Ctrl+C`を押す。時間制限なしで実行する場合は`--duration 0`を指定する。

## Step 7: 色を追跡して走行

最初は車輪を床から浮かせ、モックモードで判断だけを確認する。

```sh
python3 -m robot.color_follow_cli
```

`action=left`、`forward`、`right`、`stop`が物体の位置に合わせて表示されることを確認する。次に、車輪を浮かせたままGPIO出力を試す。

```sh
python3 -m robot.color_follow_cli --backend gpiozero
```

赤い物体が中央なら前進、左右ならその場旋回し、見失うと停止する。15秒で自動終了し、`Ctrl+C`でも停止する。車輪を床へ下ろす前に、左右の回転方向と停止を確認する。

赤い領域が`30000`以上になると、対象へ十分近づいたものとして`reason=too-close`を表示して停止する。停止距離を調整する場合は、実行中に表示される`area`を確認して値を変更する。

```sh
python3 -m robot.color_follow_cli \
  --backend gpiozero \
  --stop-area 30000
```

## Step 8: 人物を検出

最初はモーターを動かさず、OpenCV標準のHOG検出器で人物の有無と左右位置を確認する。

```sh
python3 -m robot.person_cli --duration 30
```

人物の全身が映るように2〜4mほど離れて立ち、`person=detected`と位置が表示される
ことを確認する。最後の処理画像は`captures/person-detected.jpg`へ保存される。
HOGは追加モデルなしで試せる基礎実装であり、低いアングルや上半身だけの映像では
検出しにくい。実機結果を確認してから、より軽量なAIモデルへの移行を判断する。

## Phase2 Checklist

- [ ] Camera Module 3 WideとPi 5用ケーブルを用意
- [ ] 電源OFFでカメラを接続
- [ ] `rpicam-hello --list-cameras`で認識
- [ ] `rpicam-still`で静止画撮影
- [ ] `robot.camera_cli`で静止画撮影
- [ ] 車体へカメラを固定
- [ ] 走行中の映像取得
- [ ] OpenCVで色認識
- [ ] 色追跡のモック動作確認
- [ ] 車輪を浮かせて色追跡のモーター動作確認
- [ ] 対象へ近づいたときの自動停止確認
- [ ] モーターなしで人物検出
