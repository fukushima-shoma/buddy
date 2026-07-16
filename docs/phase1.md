# Phase1: 車を動かす

## Goal

Raspberry Piから左右のDCモーターを制御して、Buddyを前後左右に動かす。

このフェーズではカメラ、AI、ROS2、Web操作はまだ扱わない。まずは「安全にモーターを回す」「Pythonから止められる」ことを最優先にする。

## Recommended Build

最初の構成は、2輪駆動 + キャスターにする。

理由:

- 部品が少ない
- 配線が単純
- 左右の速度差だけで曲がれる
- 4輪駆動より電源と制御のトラブルが少ない
- Phase2以降でカメラやセンサーを載せやすい

## Parts

必須:

- Raspberry Pi 5 4GB
- 2WDロボットカーシャーシ
- DCギアモーター 2個
- タイヤ 2個
- キャスター 1個
- TB6612FNG系デュアルモータードライバ
- ブレッドボード
- ジャンパーワイヤ
- モーター用電池ボックス
- Raspberry Pi用USB-C電源またはモバイルバッテリー

あるとよい:

- M2/M3ねじセット
- 結束バンド
- テスター
- GPIOピン番号の早見表

## Shopping List

まずは以下の組み合わせでそろえる。

| 優先 | 品目 | 買うもの |
| --- | --- | --- |
| 必須 | 車体 | 2WDスマートロボットカーシャーシキット |
| 必須 | モータードライバ | TB6612FNG デュアルモータードライバ |
| 必須 | 配線 | ジャンパーワイヤ オス-メス、オス-オス セット |
| 必須 | 試作用 | 400穴程度のブレッドボード |
| 必須 | モーター電源 | 単3電池4本用スイッチ付き電池ボックス |
| 推奨 | 工具 | 小型プラスドライバー |
| 推奨 | 固定 | M2/M3ねじセット、結束バンド |
| 推奨 | 確認 | デジタルテスター |

購入時の検索キーワード:

```text
2WD スマートロボットカー シャーシキット TTモーター
TB6612FNG デュアルモータードライバ
ジャンパーワイヤ オス メス オス オス セット
ブレッドボード 400穴
単3 4本 電池ボックス スイッチ付き
```

Amazon検索リンク:

- 2WDスマートロボットカーシャーシキット: https://www.amazon.co.jp/s?k=2WD+%E3%82%B9%E3%83%9E%E3%83%BC%E3%83%88%E3%83%AD%E3%83%9C%E3%83%83%E3%83%88%E3%82%AB%E3%83%BC+%E3%82%B7%E3%83%A3%E3%83%BC%E3%82%B7%E3%82%AD%E3%83%83%E3%83%88+TT%E3%83%A2%E3%83%BC%E3%82%BF%E3%83%BC
- TB6612FNGデュアルモータードライバ: https://www.amazon.co.jp/s?k=TB6612FNG+%E3%83%87%E3%83%A5%E3%82%A2%E3%83%AB%E3%83%A2%E3%83%BC%E3%82%BF%E3%83%BC%E3%83%89%E3%83%A9%E3%82%A4%E3%83%90
- ブレッドボード + ジャンパーワイヤ: https://www.amazon.co.jp/s?k=%E3%83%96%E3%83%AC%E3%83%83%E3%83%89%E3%83%9C%E3%83%BC%E3%83%89+%E3%82%B8%E3%83%A3%E3%83%B3%E3%83%91%E3%83%BC%E3%83%AF%E3%82%A4%E3%83%A4+%E3%82%AD%E3%83%83%E3%83%88
- 単3電池4本用スイッチ付き電池ボックス: https://www.amazon.co.jp/s?k=%E5%8D%983+4%E6%9C%AC+%E9%9B%BB%E6%B1%A0%E3%83%9C%E3%83%83%E3%82%AF%E3%82%B9+%E3%82%B9%E3%82%A4%E3%83%83%E3%83%81%E4%BB%98%E3%81%8D

避けるもの:

- L298Nモータードライバ
- 4WDシャーシ
- 18650電池前提のキット
- 説明が少なすぎるノーブランドの全部入りキット
- Raspberry Piの5Vピンからモーター給電する前提の商品

電池は最初は単3ニッケル水素充電池4本、または単3アルカリ電池4本でよい。18650リチウムイオン電池は扱いに注意が必要なので、Phase1の最初では使わない。

## Motor Driver

モータードライバはTB6612FNG系を使う。

TB6612FNGは、2つのDCモーターを個別に正転・逆転できる。Pololuの仕様では、推奨モーター電圧は4.5Vから13.5V、連続電流は1A/チャンネル、ピークは3A/チャンネル。小型ロボットカーの最初のモーター制御に合っている。

L298Nは安価でよく見かけるが、古い方式で電圧降下と発熱が大きい。Buddyでは最初からTB6612FNG系を標準にする。

## Power Policy

Raspberry Piの5Vピンからモーターへ電源を取らない。

電源は分ける:

- Raspberry Pi: USB-C電源またはモバイルバッテリー
- モーター: 電池ボックスからモータードライバへ供給

ただし、制御信号の基準をそろえるために、Raspberry PiのGNDとモータードライバのGNDは接続する。

## Initial GPIO Plan

最初のピン割り当て案:

| 用途 | GPIO |
| --- | --- |
| 左モーターPWM | GPIO 12 |
| 左モーターIN1 | GPIO 5 |
| 左モーターIN2 | GPIO 6 |
| 右モーターPWM | GPIO 13 |
| 右モーターIN1 | GPIO 20 |
| 右モーターIN2 | GPIO 21 |
| STBY | GPIO 26 |

この割り当てはPhase1の初期案。実際の配線時に、使いやすさを見て変更してよい。

## Step 1: 部品をそろえる

購入するもの:

- 2WDロボットカーシャーシキット
- TB6612FNG系デュアルモータードライバ
- ブレッドボード
- ジャンパーワイヤ
- モーター用電池ボックス

完了条件:

- 車体を仮組みできる
- 左右のモーター線をモータードライバへ接続できる

## Step 1.5: 届いたら最初に確認する

開封したら、通電前に部品を確認する。

確認するもの:

- シャーシ板
- TTモーター 2個
- タイヤ 2個
- キャスター 1個
- 電池ボックス
- ねじ、ナット、スペーサー
- TB6612FNGモータードライバ
- ブレッドボード
- ジャンパーワイヤ
- 単3電池 4本

この時点では、Raspberry Piにもモーターにもまだ電源を入れない。

完了条件:

- 不足部品がない
- 電池ボックスが単3 4本用である
- モータードライバがTB6612FNGである

## Step 1.6: 車体だけ仮組みする

まずは電子回路なしで、車体だけ組み立てる。

作業:

- 左右のTTモーターをシャーシへ固定する
- タイヤを取り付ける
- キャスターを取り付ける
- Raspberry Piとブレッドボードを載せる位置を仮決めする
- 電池ボックスを載せる位置を仮決めする

完了条件:

- 手で押すと車体がまっすぐ転がる
- モーター線が左右とも届く
- Raspberry Pi、ブレッドボード、電池ボックスを載せる場所がある

## Step 1.7: 電源方針を確認する

通電前に電源を分ける。

```text
Raspberry Pi: USB-C電源またはモバイルバッテリー
モーター: 単3電池4本の電池ボックス
```

重要:

- Raspberry Piの5Vピンからモーターへ給電しない
- モーターの電池ボックスからRaspberry Piへ給電しない
- Raspberry PiのGNDとモータードライバのGNDは接続する

## Step 2: 配線図を作る

作業:

- モータードライバのピン名を確認する
- Raspberry PiのGPIOと接続先を表にする
- モーター電源とPi電源を分けて描く
- GND共通を明記する

完了条件:

- `hardware/phase1-wiring.md` に配線表がある
- 実物のピン名と配線表が一致している

## Step 3: GPIOライブラリ確認

Raspberry Pi上でGPIO制御に使うライブラリを決める。

第一候補:

- gpiozero

完了条件:

- Raspberry Pi上でPythonからGPIO出力を試せる
- 実機用backendは `robot/gpiozero_driver.py` に追加済み
- 配線確認が終わるまでは `--backend gpiozero` を実行しない

## Step 3.5: 実機なしで制御コードを確認する

部品が届くまでの間は、mock backendでCLIと制御ロジックを確認する。

テストを実行する。

```sh
python3 -m unittest discover -s tests
```

CLIをmock backendで実行する。

```sh
python3 -m robot.motor_cli forward --duration 0 --speed 0.2
python3 -m robot.motor_cli back --duration 0 --speed 0.2
python3 -m robot.motor_cli left --duration 0 --speed 0.2
python3 -m robot.motor_cli right --duration 0 --speed 0.2
python3 -m robot.motor_cli stop
```

完了条件:

- テストが成功する
- 各コマンドで左右モーターの予定速度が表示される
- 実機用GPIO backendは、配線確定後に追加する

## Step 4: 片側モーターだけ動かす

最初は車体を浮かせた状態で、左モーターだけ短時間動かす。

完了条件:

- 左モーターが正転する
- 左モーターが逆転する
- プログラム終了時に停止する

## Step 5: 両輪を動かす

左右のモーターを制御して、車体を床でゆっくり動かす。

完了条件:

- 前進できる
- 後退できる
- 左旋回できる
- 右旋回できる
- 停止できる

## Step 6: 操作用CLIを作る

キーボード入力またはコマンド引数で動作を選べるようにする。

例:

```sh
python3 robot/motor_cli.py forward
python3 robot/motor_cli.py back
python3 robot/motor_cli.py left
python3 robot/motor_cli.py right
python3 robot/motor_cli.py stop
```

完了条件:

- コマンドでBuddyを操作できる
- 速度を低速に制限できる
- 異常時に停止できる

## Phase1 Done Checklist

| 項目 | 状態 |
| --- | --- |
| 部品選定 | ☑ |
| 部品購入 | ☐ |
| 車体仮組み | ☐ |
| 配線表作成 | ☑ |
| GPIOライブラリ確認 | ☐ |
| mock CLI確認 | ☑ |
| 左モーター単体テスト | ☐ |
| 右モーター単体テスト | ☐ |
| 前進 | ☐ |
| 後退 | ☐ |
| 左旋回 | ☐ |
| 右旋回 | ☐ |
| 停止 | ☐ |
| CLI操作 | ☐ |

## References

- Pololu TB6612FNG Dual Motor Driver Carrier: https://www.pololu.com/product/713
- Adafruit TB6612 1.2A DC/Stepper Motor Driver Breakout Board: https://www.adafruit.com/product/2448
- Raspberry Pi hardware documentation: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html
