# Phase3: 音声で会話する

## Goal

Buddyが音声を録音し、発話内容を理解して、音声で返答できる基盤を作る。

## 構成

```text
USBマイク → WAV録音 → 音声認識 → 返答生成 → 音声合成 → USBスピーカー
```

マイク・スピーカーの到着前は、録音を無音WAV、再生をモックへ置き換えて
ファイル処理とCLIを確認する。モックが既定なので、実機バックエンドを明示しない限り
音声機器へアクセスしない。

## Step 1: テスト音を生成する

```sh
python3 -m robot.audio_cli tone \
  --output captures/audio/tone.wav \
  --frequency 440 \
  --duration 1
```

WAV情報を確認する。

```sh
python3 -m robot.audio_cli inspect captures/audio/tone.wav
```

## Step 2: 機器なしで録音・再生処理を確認する

```sh
python3 -m robot.audio_cli record \
  --backend mock \
  --output captures/audio/mock-recording.wav \
  --duration 3
```

```sh
python3 -m robot.audio_cli play \
  captures/audio/mock-recording.wav \
  --backend mock
```

## Step 3: USBスピーカーフォン到着後の認識確認

USB-A端子へ有線接続し、次を実行する。

```sh
aplay -l
arecord -l
wpctl status
```

再生・録音の両方にUSB Audioデバイスが表示されることを確認する。

## Step 4: ALSAでテスト音を再生する

既定デバイスがUSBスピーカーフォンなら次を実行する。

```sh
python3 -m robot.audio_cli play \
  captures/audio/tone.wav \
  --backend alsa
```

既定でなければ、`aplay -l`のカード番号とデバイス番号を指定する。

```sh
python3 -m robot.audio_cli play \
  captures/audio/tone.wav \
  --backend alsa \
  --device plughw:2,0
```

## Step 5: ALSAで録音する

```sh
python3 -m robot.audio_cli record \
  --backend alsa \
  --device plughw:2,0 \
  --output captures/audio/microphone-test.wav \
  --duration 5
```

録音結果を同じスピーカーフォンで再生する。

```sh
python3 -m robot.audio_cli play \
  captures/audio/microphone-test.wav \
  --backend alsa \
  --device plughw:2,0
```

## Step 6: OpenAI APIで音声を文字にする

OpenAI Python SDKを仮想環境へ導入する。

```sh
python -m pip install -r requirements-phase3.txt
```

APIキーはコードや`.env`へ書かず、シェルの環境変数へ設定する。

```sh
read -s -p "OpenAI API key: " OPENAI_API_KEY
echo
export OPENAI_API_KEY
```

録音済みWAVを文字起こしする。`--backend openai`を明示したときだけAPIを呼び出す。

```sh
python -m robot.transcribe_cli file \
  captures/audio/microphone-test.wav \
  --backend openai \
  --language ja
```

録音と文字起こしを1コマンドで行う。

```sh
python -m robot.transcribe_cli record \
  --audio-backend alsa \
  --device plughw:2,0 \
  --duration 5 \
  --backend openai \
  --language ja
```

既定の文字起こしモデルは`gpt-4o-mini-transcribe`。APIキーをGitへ保存せず、
認識対象の音声だけをOpenAI APIへ送信する。

## Step 7: 認識した文章へ返答する

まず文字入力だけで返答生成を確認する。`--backend openai`を明示した場合だけ
Responses APIを呼び出す。

```sh
python -m robot.reply_cli \
  "こんにちは。あなたの名前は？" \
  --backend openai
```

録音、文字起こし、返答生成を1コマンドで行う。

```sh
python -m robot.transcribe_cli record \
  --audio-backend alsa \
  --device plughw:2,0 \
  --duration 5 \
  --backend openai \
  --language ja \
  --reply-backend openai
```

既定の返答モデルは`gpt-5.6`で、Responses APIへ一往復だけ送信する。返答は子ども向け
の短い日本語に制限し、個人情報を尋ねず、危険な相談は信頼できる大人へ誘導する。
この段階では会話履歴を保存しない。

`transcript=not-found`と表示された場合は音声を認識できていない。返答APIは呼び出さず、
`reply=skipped reason=empty-transcript`と表示して安全に終了する。マイクに近づいて話すか、
次のコマンドで録音内容を再生して入力音量を確認する。

```sh
aplay -D plughw:2,0 captures/audio/transcription-input.wav
```

## Step 8: 返答を音声で再生する

まず固定した文章を音声合成し、EMEETから再生する。

```sh
python -m robot.speech_cli \
  "こんにちは。ぼくはAIロボットのBuddyだよ。" \
  --backend openai \
  --style buddy \
  --playback-backend alsa \
  --device plughw:2,0
```

録音、文字起こし、返答生成、音声合成、再生を1コマンドで行う。

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

既定の音声合成モデルは`gpt-4o-mini-tts`、声は`marin`、話し方は`buddy`、
保存形式はWAV。`buddy`は、3歳くらいの子どもへ少しゆっくり話し、意味に沿って
自然な抑揚と間を付ける設定。用途に応じて`--style cheerful`（明るい）または
`--style calm`（落ち着いた）へ変更できる。

連続会話や文字起こし後の返答では`--speech-style`を使う。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --speech-backend openai \
  --speech-style buddy \
  --playback-backend alsa \
  --playback-device plughw:2,0 \
  --turns 2
```

生成音声は`captures/audio/reply.wav`へ保存される。聞いている人には、この声が
人間ではなくAIによる生成音声であることをあらかじめ伝える。

## Step 9: 会話を繰り返す

次のコマンドは、`Ctrl+C`を押すまで録音と返答を繰り返す。再生後は0.5秒待ってから
次の録音を始めるため、Buddy自身の声がマイクへ戻りにくい。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --memory session \
  --speech-backend openai \
  --playback-backend alsa \
  --playback-device plughw:2,0 \
  --turns 0
```

`turn=N listening=true`が出たら話し始める。音量がしきい値を超えると録音を開始し、
発話後0.8秒の無音で自動的に応答へ進む。10秒間発話がなければAPIを呼ばず、次の
ターンへ移る。`--duration 5`は発話開始後の最大録音時間になる。

有限回だけ試す場合は`--turns 2`のように指定する。声を検知しない場合は
`--speech-threshold 300`、周囲の音へ反応する場合は`--speech-threshold 800`のように
調整する。

`--memory session`を付けると、直前までの会話をOpenAI Responses APIの
`previous_response_id`で次の返答へ引き継ぐ。Buddyの安全指示は毎ターン送信し、
既定では6回返答すると文脈をリセットする。長さは`--memory-turns 4`のように変更できる。
このプログラムは文字起こしや返答の履歴ファイルを作らないが、入力音声と返答音声の
WAVには各ターンの最新内容が残る。

## 安全上の注意

- 最初は音量を小さくする。
- モーター用電池をOFFにして音声単体を確認する。
- APIキーや認証情報をGitへコミットしない。
- 音声を保存する場合は、周囲の人へ録音中であることを伝える。
- 音声合成を使う場合は、AI生成音声であることを周囲の人へ伝える。

## Phase3 Checklist

- [x] テストWAVを生成・検査
- [x] モック録音・再生
- [x] USBスピーカーフォンをOSが認識
- [x] テスト音を実機再生
- [x] マイク録音と再生
- [x] 音声認識
- [x] 返答生成
- [x] 音声合成
- [x] 会話ループ
