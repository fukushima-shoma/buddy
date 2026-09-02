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

`httpx2/_decoders.py`で`process() takes no keyword arguments`が出る場合は、
古いBrotliとの互換性問題である。依存ファイルには`Brotli>=1.2.0`を含めているため、
同じコマンドを再実行して仮想環境を更新する。

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
  --style calm \
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

既定の音声合成モデルは`gpt-4o-mini-tts`、声は`coral`、話し方は`calm`、
保存形式はWAV。`calm`は、3歳くらいの子どもへ少しゆっくり話し、若々しく優しい
声色と自然な抑揚・間を付ける設定。用途に応じて`--style buddy`（自然で温かい）
または`--style cheerful`（明るい）へ変更できる。以前の声へ戻す場合は、単体音声で
`--voice marin`、連続会話で`--speech-voice marin`を指定する。

連続会話や文字起こし後の返答では`--speech-style`を使う。

```sh
python -m robot.conversation_loop_cli \
  --audio-backend alsa-vad \
  --audio-device plughw:2,0 \
  --transcription-backend openai \
  --reply-backend openai \
  --speech-backend openai \
  --speech-style calm \
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
  --memory-turns 30 \
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

会話中に「バイバイ」「またね」「さようなら」「おしまい」を単独で話すと、Buddyは
「バイバイ。またお話ししようね。」と返し、その会話セッションを終了する。呼びかけ
開始方式では、その後`state=waiting`へ戻って次の「ねえ、バディ」を待つ。
また、発話待ちの10秒間に声が入らない状態が2回続くと、会話が終わったと判断して
お別れを言い、同じ待機状態へ戻る。回数は`--max-silence-turns`で変更できる。

`--playback-backend alsa-interruptible`では返答再生と同時にマイク音量を監視し、
既定値2500以上が2回続くと再生を中断して次の録音へ進む。EMEETのエコーで誤作動
する場合は`--barge-in-threshold`を上げて調整する。この機能は明示時だけ有効になる。

`--orientation-backend gpiozero`を明示すると、会話の録音前に人物検出を行い、人物が
左右にいる場合だけ0.12秒ずつ最大4回旋回する。人物未検出時は動かず、中央へ入るか
上限へ達すると停止する。既定値は`off`で、実機前に`mock`で判定ログを確認する。

`--memory session`を付けると、直前までの会話をOpenAI Responses APIの
`previous_response_id`で次の返答へ引き継ぐ。Buddyの安全指示は毎ターン送信し、
既定では30回返答すると文脈をリセットする。長さは`--memory-turns 20`のように変更できる。
通常は文字起こしや返答の履歴ファイルを作らないが、入力音声と返答音声のWAVには
各ターンの最新内容が残る。

セッションをまたいで残す情報は`robot.memory_cli`で保護者が登録できる。
保存先はGit対象外の`data/buddy-memory.json`で、一覧表示・個別削除・全削除が可能。
会話中の「好きな色は青」のような定型発話は、色・動物・食べ物に限って
端末内に保存する。参照と「忘れて」による削除も端末内で処理し、この永続記憶を
OpenAI APIのプロンプトへは渡さない。氏名、住所、連絡先、会話全文はプロフィール
記憶の自動保存対象にしない。

`--auto-conversation-memory`を明示すると、各ターンの文字起こしとBuddyの返答を
`data/conversation-memory.json`へ自動保存する。既定は最大100往復を保存するが、
保存履歴はOpenAI APIのプロンプトへ再送しない。音声ファイルは会話記憶へ
複製しない。メールアドレスと電話番号は保存前に置換するが、すべての個人情報を完全には
判定できないため、保護者が`robot.conversation_memory_cli list`で定期的に確認する。

```sh
python -m robot.conversation_memory_cli list --limit 20
python -m robot.conversation_memory_cli delete-session SESSION_ID
python -m robot.conversation_memory_cli clear --yes
```

### 待機・会話状態を切り替える

`--start-trigger keyboard`を付けると、起動直後は`state=waiting`で待機し、Enterを
押したときだけ会話を開始する。指定ターンが終わると待機へ戻る。待機中に`q`とEnterを
入力するか、`Ctrl+C`を押すと`state=stopped`になって終了する。

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

押しボタンをGPIO17・物理ピン11とGNDの間に接続した後は、`keyboard`を`gpio`へ
変更するとボタンで会話を開始できる。内部プルアップとチャタリング防止はコード側で
有効になる。詳しい配線は`hardware/phase1-wiring.md`を参照する。会話履歴を有効に
した場合も、新しいセッションの開始時に履歴をリセットする。

### 呼びかけで会話を始める

`--start-trigger wakeword`では、VoskがEMEETの16kHzモノラル音声を
Raspberry Pi内で処理し、「ねえ、バディ」を検出した場合だけ会話状態へ移る。
検出時は短い起動音を鳴らしてマイクを会話録音へ引き渡し、指定ターン後は再び
ウェイクワード待機へ戻る。待機中の音声はWAVへ保存せずOpenAI APIにも送信しない。
「バイバイ」で会話を終了した後も同じ待機状態になり、「ねえ、バディ」と一致する
呼びかけが検出されるまでは、ほかの音声に返答しない。

AccessKeyは不要。約48MBの軽量日本語モデルを一度ダウンロードして展開し、その
ディレクトリを`--wake-word-model`へ指定する。導入手順と実行コマンドは
`docs/commands.md`の「『ねえ、バディ』で会話を始める」を参照する。

### 3歳半向け会話モード（保護者同席の試験用）

Buddyのキャラクターは「やさしい友だち」を軸にする。子どもの発見を一緒に喜び、
失敗や言い直しを責めず、知らないことは素直に伝える。幼児語や過度なハイテンション、
毎回の口癖は避け、親しみと落ち着きのある口調を保つ。障害物や電源異常などの安全返答は、
キャラクター表現より明確さを優先する。
会話ループはROS 2に依存しない型付き状態イベントを発行する。これにより、音声機能の
モックテストを保ったまま、後からROS 2のLED・画面・動作ノードへ接続できる。

`--child-mode`を付けると、返答を原則1文、最大でも短い2文にする。質問は一度に
1つまでとし、できるだけ分かりやすい二択にする。個人情報を尋ねず、秘密や依存を
促す表現を避け、安全に関わる話は近くの信頼できる大人へつなぐ。

文字起こしには、3歳半くらいの子どもの短い日常会話であることと、色、動物、
乗り物などのよくある話題を文脈ヒントとして自動的に渡す。文字起こしが不自然、
途中で切れている、意味がはっきりしない場合、返答モデルには推測して答えず、
「○○って言った？」のように短く確認するよう指示する。動画由来の定型句など、
典型的な誤認識は会話へ渡さず再質問する。独自の文脈を試す場合は
`--transcription-prompt "乗り物の名前を話す会話です。"`のように指定できる。

聞き取りに失敗した場合、1回目はゆっくり話し直すよう音声で促す。2回続けて失敗
した場合は内容を推測せず、近くの大人と一緒に確認するよう案内する。認識に成功
すると失敗回数はリセットされる。

最初は保護者が同席し、4ターンだけ試す。

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

このモードは、子どもが単独で利用できる完成版ではない。OpenAIのUnder 18 API
Guidanceでは、13歳未満または地域のデジタル同意年齢未満の子どもの個人データを
処理する前に、APIのZero Data Retentionを実装するよう求めている。実際の子どもの
音声をAPIへ送る運用は、必要なデータ管理を確認するまで行わない。

[OpenAI Under 18 API Guidance](https://developers.openai.com/api/docs/guides/safety-checks/under-18-api-guidance)

## Step 10: systemdで会話待機を自動起動する

`infra/buddy-conversation.service`は、ラズパイの起動後に会話プログラムを自動起動し、
異常終了時は5秒後に再起動する。APIキーはGit対象外の`/home/shofukus/buddy/.env`から
読み込む。会話の開始方式はウェイクワード、会話履歴はローカル自動保存、人物追従と
モーター旋回は起動時には停止している。呼びかけ後に「ついてきて」と完全一致する発話を
認識すると確認を返し、続けて「はい」と完全一致する発話を認識した場合だけ人物追従を
開始する。「止まって」「ストップ」「バイバイ」で停止する。
返答再生中の「止まって」「ストップ」はVoskでローカル認識して即時停止する。
空白や記号だけの結果、動画由来の定型句、異常に長い文字起こしは返答モデルへ
渡さず、もう一度話すよう聞き返す。
「進んで」「動いて」のように方向や動作が曖昧な指示では動かず、指示が分からないことを
返す。確認中も「やめる」で開始を取り消し、ほかの発話では動かず再確認する。
現在の低電圧は`vcgencmd get_throttled`で監視し、走行開始の拒否と走行中の停止に使う。
`--child-games`では、なぞなぞ、どうぶつクイズ、のりものクイズを状態付きで進行する。

導入、ログ確認、停止方法は`docs/commands.md`の
「ラズパイ起動時にBuddyも自動起動する」を参照する。

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
