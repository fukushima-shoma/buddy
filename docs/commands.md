# Buddy コマンド説明書

Raspberry Pi上でBuddyの動作確認、カメラ撮影、色検出、色追跡を行うためのコマンド集。

## 事前準備

作業ディレクトリへ移動する。

```sh
cd ~/buddy
```

GitHubの最新版を取得する。

```sh
git pull origin main
```

Pythonモジュールはプロジェクトのルートで、`python3 -m robot...`の形式で実行する。別のディレクトリから実行すると`No module named 'robot'`になる。

## 自動テスト

実機を動かさず、モーター制御などのロジックを確認する。

```sh
python3 -m unittest discover -s tests -v
```

すべての項目が`ok`になり、最後に`OK`と表示されれば成功。

## モーター単体テスト

実機を動かす前に、車輪を床から浮かせる。

前進:

```sh
python3 -m robot.motor_cli forward \
  --backend gpiozero \
  --speed 1 \
  --max-speed 1 \
  --duration 1
```

後退、左旋回、右旋回、停止は先頭の動作名を変更する。

```sh
python3 -m robot.motor_cli back --backend gpiozero --speed 1 --max-speed 1 --duration 1
python3 -m robot.motor_cli left --backend gpiozero --speed 1 --max-speed 1 --duration 1
python3 -m robot.motor_cli right --backend gpiozero --speed 1 --max-speed 1 --duration 1
python3 -m robot.motor_cli stop --backend gpiozero
```

主なオプション:

| オプション | 意味 |
| --- | --- |
| `--backend gpiozero` | Raspberry PiのGPIOで実機を動かす |
| `--backend mock` | GPIOを使わず計算結果だけ確認する |
| `--speed` | 指定速度。範囲は0.0〜1.0 |
| `--max-speed` | 許可する最高速度 |
| `--duration` | 動かす秒数 |
| `--left-scale` | 左モーターの補正値 |
| `--right-scale` | 右モーターの補正値 |

Buddyの実機では左`0.95`、右`1.0`を基本の補正値として使用する。

## キーボードによる手動運転

```sh
python3 -m robot.keyboard_cli --backend gpiozero
```

| キー | 動作 |
| --- | --- |
| `W` | 前進 |
| `A` | 左旋回 |
| `S` | 後退 |
| `D` | 右旋回 |
| `Space` | 停止 |
| `Q` | 終了 |

キー入力が一定時間途切れた場合も自動停止する。

## カメラの認識確認

OSから認識されているカメラを一覧表示する。

```sh
rpicam-hello --list-cameras
```

Camera Module 3では通常`imx708`が表示される。

## 静止画撮影

Raspberry Pi標準コマンドで撮影する。

```sh
mkdir -p captures
rpicam-still --zsl -o captures/rpicam-test.jpg
```

BuddyのPythonコードから撮影する。

```sh
python3 -m robot.camera_cli \
  --backend picamera2 \
  --output captures/latest.jpg
```

`captured=captures/latest.jpg`と表示されれば保存成功。

## Macへ画像をコピー

Mac側のターミナルで実行する。

```sh
scp pi@buddy.local:~/buddy/captures/latest.jpg .
```

ユーザー名やホスト名が異なる場合は`pi@buddy.local`を変更する。

## 静止画から色を検出

```sh
python3 -m robot.color_cli \
  --input captures/latest.jpg \
  --color red \
  --output captures/color-detected.jpg
```

成功例:

```text
detected=true color=red position=center center=(320,240) area=5000
```

`--color`には`red`、`green`、`blue`を指定できる。`--min-area`より小さな色領域はノイズとして無視される。

## リアルタイム色検出

モーターを動かさず、カメラ映像から赤い物体を検出する。

```sh
python3 -m robot.live_color_cli --color red
```

標準では15秒間、5fpsで処理する。時間制限なしで実行する場合:

```sh
python3 -m robot.live_color_cli \
  --color red \
  --duration 0
```

終了は`Ctrl+C`。最後の処理画像は`captures/live-color.jpg`へ保存される。

高速で動く対象を検出する場合:

```sh
python3 -m robot.live_color_cli \
  --color red \
  --fps 20 \
  --min-area 500 \
  --duration 0
```

`--fps`を上げると確認間隔が短くなる。`--min-area`を小さくすると小さな対象を検出しやすくなるが、誤検出も増える。

## 色追跡走行

最初は実機を動かさないモックモードで、判断結果だけを確認する。

```sh
python3 -m robot.color_follow_cli
```

実機で追跡する場合は、最初に車輪を浮かせて実行する。

```sh
python3 -m robot.color_follow_cli \
  --backend gpiozero \
  --duration 15 \
  --stop-area 30000
```

判断ルール:

| 検出状態 | 表示 | 車体の動作 |
| --- | --- | --- |
| 対象が左 | `action=left reason=tracking` | 左旋回 |
| 対象が中央 | `action=forward reason=tracking` | 前進 |
| 対象が右 | `action=right reason=tracking` | 右旋回 |
| 未検知 | `action=stop reason=not-found` | 停止 |
| 対象が近い | `action=stop reason=too-close` | 停止 |

高速で動く対象を追跡する場合:

```sh
python3 -m robot.color_follow_cli \
  --backend gpiozero \
  --fps 20 \
  --min-area 500 \
  --stop-area 30000 \
  --duration 15
```

`stop-area`は画像内の対象面積であり、実際の距離ではない。

- 値を小さくする: 遠い段階で停止する
- 値を大きくする: より近づいてから停止する

## 距離センサーを測定

Raspberry Pi OSでは仮想環境を有効化して実行する。

```sh
cd ~/buddy
source .venv/bin/activate
```

まずモックでCLIを確認する。

```sh
python -m robot.distance_cli \
  --backend mock \
  --mock-distance 18 \
  --stop-distance 20 \
  --duration 1
```

VL53L1X実機で15秒間測定する。モーター用電池はOFFのまま実行する。

```sh
python -m robot.distance_cli \
  --backend vl53l1x \
  --stop-distance 20 \
  --duration 15
```

出力例:

```text
distance=65.0cm obstacle=false
distance=18.0cm obstacle=true
```

`obstacle=true`は測定距離が`--stop-distance`以下であることを表す。この段階では判定を表示するだけで、モーターは制御しない。

## GPIOが使用中と表示された場合

`GPIO busy`は、別のプログラムがGPIOを使用している状態を表す。

```sh
pgrep -af 'python3.*robot'
```

残っているプロセスのPIDを確認して終了する。

```sh
kill PID
```

終了しない場合に限り:

```sh
kill -9 PID
```

解消しない場合はRaspberry Piを再起動する。

```sh
sudo reboot
```

複数のモーター制御コマンドを同時に実行しない。

## よく使うオプションの関係

| オプション | 小さくした場合 | 大きくした場合 |
| --- | --- | --- |
| `--fps` | 処理が軽いが高速な対象を逃しやすい | 高速な対象を追いやすいが負荷が増える |
| `--min-area` | 小さな対象も拾うが誤検出が増える | ノイズに強いが遠い対象を逃しやすい |
| `--stop-area` | 遠くで停止する | 近くまで進む |
| `--duration` | 短時間で安全に終了する | 長時間動作する。`0`は無制限 |
| `--speed` | ゆっくり動く。ただしモーターが回らない場合がある | 速く動く |

## 安全上の注意

- 初めてのモーターコマンドは必ず車輪を浮かせて実行する。
- Raspberry Piとモーターの電源は分け、GNDだけを共通にする。
- `--duration 0`を使用した場合は、終了するまでGPIOやカメラを占有する。
- 実機走行中はすぐに`Ctrl+C`または電源スイッチへ手が届く位置にいる。
- 色追跡の面積は実距離ではない。距離センサー搭載後は、センサーによる停止を優先する。
