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

## CPU・メモリ使用率の監視

Raspberry Pi上で次の情報を2秒間隔で表示する。終了するには`Ctrl+C`を押す。

- `/proc/stat`から計算したCPU使用率
- `uptime`のロードアベレージ
- `free -h`のメモリ使用量
- `ps`のCPU使用率上位プロセス
- `vcgencmd measure_temp`のCPU温度
- `vcgencmd get_throttled`の電圧低下・温度制限フラグ

```sh
scripts/monitor_buddy_resources.sh
```

表示間隔と取得回数を指定する場合は、次のように実行する。

```sh
scripts/monitor_buddy_resources.sh --interval 5 --count 12
```

このコマンドは読み取り専用で、サービスやハードウェアの状態を変更しない。総合診断の
`scripts/collect_buddy_diagnostics.sh`にも1回分のCPU・メモリ使用率が含まれる。

## 音声入出力（Phase3）

マイク・スピーカー到着前はモックでWAV処理を確認できる。詳細は
[`docs/phase3.md`](phase3.md)を参照する。

```sh
python3 -m robot.audio_cli tone --output captures/audio/tone.wav
python3 -m robot.audio_cli inspect captures/audio/tone.wav
python3 -m robot.audio_cli record --backend mock --duration 3
python3 -m robot.audio_cli play captures/audio/recording.wav --backend mock
```

録音済みWAVをOpenAI APIで日本語文字起こしする。

```sh
python -m robot.transcribe_cli file \
  captures/audio/microphone-test.wav \
  --backend openai \
  --language ja
```

EMEETで5秒録音し、そのまま文字起こしする。

```sh
python -m robot.transcribe_cli record \
  --audio-backend alsa \
  --device plughw:2,0 \
  --duration 5 \
  --backend openai \
  --language ja
```

文字入力からBuddyの返答を生成する。

```sh
python -m robot.reply_cli "こんにちは。あなたの名前は？" --backend openai
```

録音、文字起こし、返答生成を続けて行う。

```sh
python -m robot.transcribe_cli record \
  --audio-backend alsa \
  --device plughw:2,0 \
  --duration 5 \
  --backend openai \
  --language ja \
  --reply-backend openai
```

`transcript=not-found`の場合は、録音内容を再生してマイク入力を確認する。

```sh
aplay -D plughw:2,0 captures/audio/transcription-input.wav
```

OpenAI APIで文章を音声合成し、EMEETから再生する。

```sh
python -m robot.speech_cli \
  "こんにちは。ぼくはAIロボットのBuddyだよ。" \
  --backend openai \
  --style calm \
  --playback-backend alsa \
  --device plughw:2,0
```

声は`coral`、話し方は`calm`が既定。若々しく優しい声色と、少しゆっくりした
自然な抑揚を使う。`--style buddy`と明るい`--style cheerful`も選択できる。
連続会話と`transcribe_cli`では同じ設定を`--speech-style`で指定する。以前の声へ
戻す場合は`--voice marin`または`--speech-voice marin`を指定する。

録音から返答の音声再生までを続けて行う。

```sh
python -m robot.transcribe_cli record \
  --audio-backend alsa \
  --device plughw:2,0 \
  --duration 5 \
  --backend openai \
  --language ja \
  --reply-backend openai \
  --speech-backend openai \
  --playback-backend alsa \
  --playback-device plughw:2,0
```

生成音声は`captures/audio/reply.wav`へ保存される。利用時はAI生成音声であることを
周囲の人へ伝える。

録音と音声返答を`Ctrl+C`まで繰り返す。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --memory session \
  --memory-turns 30 \
  --speech-backend openai \
  --speech-style calm \
  --playback-backend alsa-interruptible \
  --playback-device plughw:2,0 \
  --turns 0
```

`turn=N listening=true`の後に話すと、発話後0.8秒の無音で応答へ進む。10秒間発話が
なければAPIを呼ばず次へ進む。`--turns 2`なら2回で終了する。声を拾わない場合は
`--speech-threshold 300`、雑音を拾う場合は`--speech-threshold 800`を試す。
`--memory session`は会話の文脈を引き継ぎ、既定では30返答ごとにリセットする。
文字の履歴ファイルは作らないが、最新ターンの入出力WAVは保存される。
会話中に「バイバイ」「またね」「さようなら」「おしまい」のいずれかを単独で話すと、
Buddyがお別れを返して、その会話セッションを指定ターン数より前に終了する。

好きな色など、保護者が確認した固定プロフィールはローカル記憶で管理する。

```sh
python -m robot.memory_cli set 好きな色 青
python -m robot.memory_cli set 好きな動物 ぞう
python -m robot.memory_cli list
python -m robot.memory_cli delete 好きな色
```

全削除は確認用の`--yes`が必要になる。

```sh
python -m robot.memory_cli clear --yes
```

記憶は`data/buddy-memory.json`だけに保存され、Gitの対象外になる。会話コマンドは
このファイルが存在すると保護者登録情報を読み込む。

会話そのものを次回の会話でも覚えさせる場合は、会話コマンドへ次を追加する。

```sh
--auto-conversation-memory \
--conversation-memory-turns 20
```

文字起こしとBuddyの返答を`data/conversation-memory.json`へ自動保存する。音声は会話
記憶へ複製しない。最大100往復だけを残し、新しい会話セッションの開始時に直近20往復を
参考情報として渡す。メールアドレスと電話番号は保存前に自動で置換される。ただし、氏名や
住所などを完全に自動判別するものではないため、保護者が定期的に内容を確認する。

```sh
python -m robot.conversation_memory_cli list --limit 20
python -m robot.conversation_memory_cli delete-session SESSION_ID
python -m robot.conversation_memory_cli clear --yes
```

`list`に表示された`session=`の値を`delete-session`へ渡すと、その会話だけを削除できる。
記憶ファイルはGit対象外だが、ラズパイを譲渡・廃棄するときは`clear --yes`で消去する。

3歳半向けの短い返答、1つの質問、二択、聞き取り失敗時の音声再質問を有効にする。
保護者同席で、最初は有限ターンかつ履歴なしで試す。
子どもの短い日常会話を文字起こしの文脈ヒントとして自動送信し、典型的な誤認識文は
会話へ渡さない。不自然な内容には、推測せず短い確認質問を返す。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --child-mode \
  --memory none \
  --speech-backend openai \
  --speech-style calm \
  --playback-backend alsa \
  --playback-device plughw:2,0 \
  --turns 4
```

これは保護者同席の開発試験用。実際の13歳未満の子どもの音声をOpenAI APIへ送る
前に、Under 18 API Guidanceに従い、Zero Data Retentionを含む必要なデータ管理を
確認する。

### 待機してから会話を始める

まずは追加部品なしで、Enterキーを押すと4ターンの会話を開始する。会話が終わると
`state=waiting`へ戻る。待機中に`q`とEnterを入力すると終了する。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --child-mode \
  --memory none \
  --speech-backend openai \
  --speech-style calm \
  --playback-backend alsa \
  --playback-device plughw:2,0 \
  --turns 4 \
  --start-trigger keyboard
```

GPIO17・物理ピン11とGNDの間に押しボタンを接続した場合は、開始方式を`gpio`へ
変更する。ボタンを1回押すたびに4ターン会話し、その後は再び待機する。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --child-mode \
  --memory none \
  --speech-backend openai \
  --speech-style calm \
  --playback-backend alsa \
  --playback-device plughw:2,0 \
  --turns 4 \
  --start-trigger gpio \
  --button-pin 17
```

`--sessions 1`を付けると1回の会話セッション後に終了する。省略時は、キーボードの
`q`または`Ctrl+C`で止めるまで待機と会話を繰り返す。`--memory session`を指定しても
会話メモリは各セッション開始時にリセットされ、前に利用した人の会話を次の人へ
引き継がない。

### 「ねえ、バディ」で会話を始める

ウェイクワードはVoskを使ってRaspberry Pi内で検出する。AccessKeyや外部サービスは
不要で、待機中の音声は保存もOpenAI APIへの送信もしない。ウェイクワードを検出した
後の会話だけを既存の文字起こしへ渡す。
誤起動を抑えるため、途中認識では起動せず、最終認識が「ねえ バディ」と完全一致した
場合だけ会話を開始する。「ねえ」または「バディ」だけでは起動しない。
会話終了後はスピーカーの残響を拾わないよう、標準で1.5秒待ってから判定を再開する。
必要なら`--wake-word-rearm-delay`で待ち時間を変更できる。

最新版の依存パッケージを仮想環境へ追加する。

```sh
python -m pip install -r requirements-phase3.txt
```

`httpx2/_decoders.py`で`process() takes no keyword arguments`が出た場合も、
このコマンドで`Brotli>=1.2.0`へ更新する。

Voskの軽量日本語モデル（約48MB）を取得して展開する。モデルはGitへ追加しない。

```sh
mkdir -p models/wakeword
curl -L \
  https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip \
  -o /tmp/vosk-model-small-ja-0.22.zip
unzip /tmp/vosk-model-small-ja-0.22.zip -d models/wakeword
```

モデルを展開したら、呼びかけ開始方式で起動する。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --child-mode \
  --memory session \
  --memory-turns 30 \
  --auto-conversation-memory \
  --conversation-memory-turns 20 \
  --speech-backend openai \
  --speech-style calm \
  --playback-backend alsa-interruptible \
  --playback-device plughw:2,0 \
  --turns 0 \
  --max-silence-turns 2 \
  --start-trigger wakeword \
  --wake-word-model models/wakeword/vosk-model-small-ja-0.22
```

`state=waiting trigger=wakeword`の間に「ねえ、バディ」と呼ぶ。検出すると短い起動音が
鳴り、`state=conversation`へ切り替わる。会話は最大30返答分の文脈を引き継ぐ。
以前のセッションからは、ローカルに保存した直近20往復だけを参考情報として引き継ぐ。
会話中に「バイバイ」と話した場合も、お別れ音声の後で呼びかけ待ちへ戻る。
待機中は「ねえ、バディ」と一致する呼びかけだけを受け付け、それ以外の会話や
「バイバイ」には返答せず、録音ファイルへの保存やOpenAI APIへの送信も行わない。
10秒間の無音が2回続いた場合も、「お話はおしまいかな。またお話ししようね。」と
話して待機へ戻る。無効化する場合は`--max-silence-turns 0`を指定する。
Buddyの返答中に大きめの声が2回連続で検出されると再生を止め、次の録音へ進む。
人物追従中の「止まって」「ストップ」はVoskでローカル認識するため、返答中でも
一度言うだけで再生中断、モーター停止、停止音声まで行う。この停止処理はOpenAI APIを
待たない。それ以外の言葉で音声だけを中断した場合は、その内容を次の録音でもう一度話す。
スピーカー自身の音で止まる場合は`--barge-in-threshold 3500`のように上げる。
割り込みを使わない場合は`--playback-backend alsa`へ戻す。
標準の呼びかけは`ねえ バディ`。別の言い方を試す場合は、例えば
`--wake-phrase バディ`を追加する。`models/wakeword/`は`.gitignore`で除外している。

### ラズパイ起動時にBuddyも自動起動する

APIキーをGit対象外の`.env`へ保存する。すでに`.env`がある場合は上書きしない。

```sh
cd ~/buddy
cp -n .env.example .env
nano .env
chmod 600 .env
```

`.env`の`OPENAI_API_KEY=`の後ろへAPIキーを記入する。サービスは、EMEETの安定した
ALSAカード名`plughw:CARD=Plus,DEV=0`を使うため、再起動後にカード番号が変わっても
影響を受けにくい。次の導入スクリプトは、仮想環境、`.env`、Voskモデルが揃っている
ことを確認してからサービスを有効にする。

```sh
cd ~/buddy
chmod +x scripts/install_buddy_service.sh
./scripts/install_buddy_service.sh
```

導入後はラズパイを起動するとBuddyも立ち上がり、`ねえ、バディ`の呼びかけ待ちに入る。
会話履歴の自動保存と、呼びかけ後の音声による人物追従操作も有効になる。起動しただけで
モーターが走り出すことはなく、会話前の旋回も行わない。

人物追従を始める場合は、必ず周囲を片付け、最初は車輪を床から浮かせる。

1. 「ねえ、バディ」と呼び、起動音を待つ
2. 「ついてきて」と単独で話す
3. Buddyの「ついていってもいい？」という確認を待つ
4. 「はい」と単独で答えると、Buddyが開始を知らせて人物追従を開始する

「ついてきて」と、それに続く「はい」がそれぞれ完全一致した場合だけ走行命令になる。
「ついてきてって言って」のような別の文では開始しない。確認中に「やめる」と言うと
取り消し、それ以外の曖昧な返答でも開始しない。「進んで」「動いて」のように方向や
動作が曖昧な指示でも動かない。走行中は無言でも会話セッションを終了せず、停止命令を
待ち続ける。
開始時は「いまから、ついていくね。動き始めるよ。」と音声で知らせる。
「止まって」または「ストップ」で直ちに人物追従を停止し、「バイバイ」では人物追従を
停止してから呼びかけ待ちへ戻る。停止時は「止まったよ。もう動かないよ。」と知らせる。
すでに停止中なら「いまは止まっているよ。」と返す。聞き取りに失敗した場合に備え、
実機走行中はモーター用電池のスイッチへすぐ手が届く位置で見守る。

ラズパイの現在の低電圧状態は`vcgencmd get_throttled`で監視する。低電圧中は
「ついてきて」と言っても人物追従を開始せず、走行中に低電圧を検出した場合は停止して
「電源が弱くなっているから、安全のために止まるね。」と知らせる。「電池は大丈夫？」
または「バッテリーは大丈夫？」と聞くと現在の状態を答える。モバイルバッテリーから
残量の百分率は取得できないため、この機能はラズパイの低電圧警告を監視する。

子ども向けの遊びは、呼びかけ後に次の言葉で開始する。

- 「なぞなぞしよう」
- 「どうぶつクイズ」
- 「のりものクイズ」

問題を聞き直す場合は「もう一回」、遊びだけを終える場合は「おしまい」と話す。ゲーム中の
「おしまい」は会話全体を終了せず、「ゲームはおしまい。また遊ぼうね。」と返して通常会話へ
戻る。「バイバイ」はゲーム中でも会話全体と人物追従を終了する。

状態とログを確認する。

```sh
sudo systemctl status buddy-conversation.service
sudo journalctl -u buddy-conversation.service -f
```

一時停止、再開、設定変更後の再起動は次のとおり。

```sh
sudo systemctl stop buddy-conversation.service
sudo systemctl start buddy-conversation.service
sudo systemctl restart buddy-conversation.service
```

OS起動時の自動起動を解除する場合は、停止と無効化を同時に行う。

```sh
sudo systemctl disable --now buddy-conversation.service
```

サービス設定はRaspberry Piのユーザー`shofukus`、配置先`/home/shofukus/buddy`を前提と
する。ユーザー名や配置先を変えた場合は`infra/buddy-conversation.service`内の
`User`、`Group`、各パスを合わせて変更する。

更新後にサービス設定を反映する場合も、導入スクリプトを再実行する。

```sh
cd ~/buddy
./scripts/install_buddy_service.sh
```

会話開始前に人物の方向へ短く旋回する機能は、まずモーターを動かさないモックで
カメラ判定だけを確認する。

```sh
# 上の会話コマンドへ追加
--orientation-backend mock
```

`orientation=left/right reason=aligning`または`person-centered`が確認できたら、周囲を
片付け、最初は車輪を床から浮かせて次を試す。

```sh
# 上の会話コマンドへ追加
--orientation-backend gpiozero \
--orientation-speed 1 \
--orientation-pulse 0.12 \
--orientation-attempts 4
```

人物を検出できない場合は旋回しない。1回0.12秒、最大4回だけ旋回し、各動作後に
必ず停止する。キャスターの向きや周囲の障害物は画像だけでは保証できないため、
保護者の監視下で調整する。通常は`--orientation-backend off`で無効になる。

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
