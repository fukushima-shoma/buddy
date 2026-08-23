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

既定値は左`1.0`、右`1.0`で、左右へ同じ出力を与える。車体が曲がる場合だけ、
`--left-scale`または`--right-scale`を指定して補正する。

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

Buddyの実機環境で調整した既定値は、`fps=10`、`min-area=50`、
`stop-area=250000`、`stop-distance=60cm`、`resume-distance=70cm`、
`lost-frame-tolerance=1`、`turn-pulse=0.08秒`。距離センサーを含む通常の
追跡は次の短いコマンドで実行できる。

```sh
python3 -m robot.color_follow_cli \
  --backend gpiozero \
  --distance-backend vl53l1x
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

一瞬の未検出による停止と、旋回による対象の追い越しを抑える場合:

```sh
python3 -m robot.color_follow_cli \
  --backend gpiozero \
  --fps 10 \
  --min-area 100 \
  --lost-frame-tolerance 1 \
  --turn-pulse 0.08 \
  --duration 15
```

`--lost-frame-tolerance 1`は1フレームだけ最後の検出を保持する。連続して
見失った場合は従来どおり停止する。`--turn-pulse 0.08`は80ミリ秒だけ旋回して
停止し、次のカメラ画像で方向を判断し直す。距離センサーによる障害物停止は
これらより常に優先される。

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

## 距離センサー付き色追跡

最初はモーターモックと距離センサーモックで統合判断を確認する。

```sh
python -m robot.color_follow_cli \
  --backend mock \
  --distance-backend mock \
  --mock-distance 15 \
  --stop-distance 20
```

赤い物体が見えていても、`reason=obstacle`と`action=stop`が表示される。

次に、車輪を床から浮かせてカメラ・距離センサー・モーターを統合する。

```sh
python -m robot.color_follow_cli \
  --backend gpiozero \
  --distance-backend vl53l1x \
  --stop-distance 20 \
  --duration 15
```

距離センサーを使用する場合の優先順位:

1. 距離が未取得なら`reason=distance-not-ready`で停止
2. 20cm以下なら`reason=obstacle`で停止
3. 色を見失ったら停止
4. 色領域が大きすぎたら停止
5. 安全な距離なら色の位置に従って追跡

既定では60cm以下で一度障害物停止すると、70cm以上へ離れるまで停止を保持する。
この差をヒステリシスと呼び、距離の境界付近で停止と再発進を繰り返すのを防ぐ。
変更する場合は`--stop-distance`と`--resume-distance`を指定し、再開距離は停止距離
以上にする。

## 人物検出（モーターなし）

OpenCV Zooの軽量MediaPipe人物検出モデルで、カメラに映った人物の有無と左右位置を
確認する。このコマンドはモーターを制御しない。初回だけモデルを導入する。

```sh
bash scripts/install_person_model.sh
```

```sh
python3 -m robot.person_cli --duration 30
```

成功例:

```text
person=detected position=center center=(320,240) confidence=0.84
person=not-found
snapshot=captures/person-detected.jpg
```

人物が背景と区別しやすい明るい場所で試す。既定値は5fps、信頼度0.45。
検出しにくい場合は信頼度の下限を少し下げる。

```sh
python3 -m robot.person_cli \
  --duration 30 \
  --min-confidence 0.4
```

`--min-confidence`を下げると検出しやすくなるが、家具などの誤検出も増える。
最後の枠付き画像は`captures/person-detected.jpg`へ保存される。

比較用に従来のHOG全身検出も残している。

```sh
python3 -m robot.person_cli \
  --backend hog \
  --fps 2 \
  --min-confidence 0.2 \
  --duration 30
```

## 人物検出・距離センサー・モーターの統合

人物の位置と距離から走行判断を行う。モーターバックエンドの既定は`mock`なので、
`--backend gpiozero`を明示しない限り実機モーターは動かない。

最初に100cm固定のモック距離で確認する。

```sh
python3 -m robot.person_follow_cli \
  --backend mock \
  --distance-backend mock \
  --mock-distance 100 \
  --duration 30
```

人物が中央なら`action=forward`、左右なら`action=left/right`、人物がいなければ
`reason=not-found`で`action=stop`になる。

次にVL53L1X実機を使用する。

```sh
python3 -m robot.person_follow_cli \
  --backend mock \
  --distance-backend vl53l1x \
  --duration 30
```

60cm以下では人物の位置に関係なく`reason=obstacle`で停止し、70cm以上へ離れるまで
停止を保持する。距離がまだ取得できず人物が中央または未検出なら
`reason=distance-not-ready`で停止する。距離が未取得でも人物が左右にいる場合は、
前進せず短い旋回だけ行い、距離センサーを人物へ向け直す。このときは
`reason=distance-not-ready-turning`を出力する。
最後の枠付き画像は`captures/person-follow.jpg`へ保存される。

誤検出や一時的な値の揺れを抑える既定の安定化:

- 直近3フレーム中2回、水平中心差160px以内で人物を検出するまで
  `reason=person-confirming`で停止
- 追跡開始後は1フレームだけ未検出を許容
- 直近3回の人物中心位置の中央値で`left/center/right`を決定
- 直近3回の距離の中央値で単発の距離スパイクを除外
- 生の距離が60cm以下なら中央値を待たず即座に停止
- 停止解除は70cm以上を5フレーム連続確認してから実行
- 人物枠は直近3回の面積中央値をログへ記録するが、既定では停止に使用しない

必要な場合は次のオプションで変更できる。

```sh
python3 -m robot.person_follow_cli \
  --distance-backend vl53l1x \
  --person-confirm-window 3 \
  --person-confirm-hits 2 \
  --person-confirm-max-shift 160 \
  --lost-frame-tolerance 1 \
  --position-window 3 \
  --distance-window 3 \
  --resume-confirm-frames 5 \
  --stop-person-area 0 \
  --resume-person-area 140000 \
  --person-area-window 3 \
  --person-area-stop-confirm-frames 2 \
  --person-area-resume-confirm-frames 3 \
  --duration 30
```

ログの`raw-area`と`raw-distance`は現在フレームの生値、`area`と`distance`は中央値
などの安定化後の値。MediaPipeが推定した人物枠は姿勢で大きく変動するため、既定の
`--stop-person-area 0`では記録だけを行い、停止判定には使用しない。画像による補助
停止を実験する場合だけ正の値を指定する。人物を完全に見失うと面積履歴をリセット
する。距離の生値は平滑化より先に停止判定へ
使うため近距離では即停止し、遠距離への単発スパイクでは再開しない。

人物取得は連続検出ではなく、直近3フレーム中2回の多数決を使う。1フレームの姿勢
変化を許容しつつ、2回の水平中心が160pxより離れている場合は別候補として追跡を
開始しない。

判断ログが安定したら、車輪を床から浮かせ、モーター用電池をONにして15秒だけ
実機モーターを確認する。

```sh
python3 -m robot.person_follow_cli \
  --backend gpiozero \
  --distance-backend vl53l1x \
  --duration 15
```

人物が中央なら前進、左右なら80ミリ秒だけパルス旋回し、次の画像で方向を判断し直す。
人物の確認中・消失、距離未取得、60cm以下の障害物では即座に停止する。車輪を床へ
下ろす前に、前進・左右旋回・すべての停止理由を確認する。

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
| `--stop-distance` | 対象の近くで停止する | 対象から離れて停止する |
| `--resume-distance` | 障害物停止から早く再開する | 十分離れるまで停止を保持する |
| `--duration` | 短時間で安全に終了する | 長時間動作する。`0`は無制限 |
| `--speed` | ゆっくり動く。ただしモーターが回らない場合がある | 速く動く |
| `--lost-frame-tolerance` | 見失うとすぐ停止する | 瞬間的な未検出に強いが停止が遅れる |
| `--turn-pulse` | 細かく旋回して再確認する | 大きく旋回するが対象を追い越しやすい |

## 安全上の注意

- 初めてのモーターコマンドは必ず車輪を浮かせて実行する。
- Raspberry Piとモーターの電源は分け、GNDだけを共通にする。
- `--duration 0`を使用した場合は、終了するまでGPIOやカメラを占有する。
- 実機走行中はすぐに`Ctrl+C`または電源スイッチへ手が届く位置にいる。
- 色追跡の面積は実距離ではない。距離センサー搭載後は、センサーによる停止を優先する。
