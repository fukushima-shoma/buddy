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

## 安全上の注意

- 最初は音量を小さくする。
- モーター用電池をOFFにして音声単体を確認する。
- APIキーや認証情報をGitへコミットしない。
- 音声を保存する場合は、周囲の人へ録音中であることを伝える。

## Phase3 Checklist

- [x] テストWAVを生成・検査
- [x] モック録音・再生
- [x] USBスピーカーフォンをOSが認識
- [x] テスト音を実機再生
- [x] マイク録音と再生
- [ ] 音声認識
- [ ] 返答生成
- [ ] 音声合成
- [ ] 会話ループ
