# Buddy

自走AIカー「Buddy」を作るプロジェクト。

## Goal

子どもと遊べるAIロボットカーを作る。

## Roadmap

| Phase | 期間 | ゴール | 主な成果物 |
| --- | --- | --- | --- |
| Phase0 | 2週間 | 開発環境構築 | Raspberry Piセットアップ |
| Phase1 | 1〜2か月 | 車を動かす | 前後左右に走るロボットカー |
| Phase2 | 2か月 | カメラ搭載 | 人や色を認識する車 |
| Phase3 | 2か月 | AI搭載 | 音声で会話する車 |
| Phase4 | 2〜3か月 | ROS2 | ノード分割されたロボット |
| Phase5 | 3か月 | 自律走行 | 家の地図を作る |
| Phase6 | 2か月 | クラウド接続 | Web画面から操作 |
| Phase7 | 3〜6か月 | AIエージェント | 子どもと遊べるBuddy完成 |

## Current Phase

Phase5開始: URDFとTFを土台に自律走行へ進む

詳細手順:

- [子どもとの実会話からの改善項目](docs/conversation-improvements.md)
- [自然な会話に向けたRealtime移行](docs/realtime-migration.md)
- [スマホで会話状態を見る](docs/conversation-display.md)
- [ログからセッションを評価する](docs/session-evaluation.md)
- [セッションをまたぐ会話索引](docs/conversation-memory.md)
- [会話の遅延と改善方針](docs/conversation-latency-analysis.md)
- [固定音声キャッシュとTTSチャンク比較](docs/fixed-speech-cache.md)
- [応答速度改善の取り込み・A/B検証計画](docs/voice-latency-adoption-plan.md)
- [Buddyのキャラクター設定](docs/buddy-identity.md)
- [Buddy コマンド説明書](docs/commands.md)
- [docs/phase0.md](docs/phase0.md)
- [docs/phase1.md](docs/phase1.md)
- [docs/phase2.md](docs/phase2.md)
- [docs/phase3.md](docs/phase3.md)
- [docs/phase4.md](docs/phase4.md)
- [docs/phase5.md](docs/phase5.md)

## Phase0 Checklist

- [x] GitHubリポジトリを作成する
- [x] Macの開発環境を整える
- [x] Raspberry Pi OSをインストールする
- [x] Raspberry Piを起動する
- [x] SSH接続を有効化する
- [x] Raspberry PiのLinuxを更新する
- [x] Raspberry PiでGitを設定する
- [x] VS Code Remote SSHで接続する
- [x] Raspberry PiでPythonを実行する
- [x] プロジェクト構成を作成する
- [x] READMEを整備する

## Phase1 Policy

最初の車体は、2輪駆動 + キャスターで作る。

- 左右2つのDCモーターを独立制御する
- モータードライバはTB6612FNG系を使う
- Raspberry Pi本体とモーターの電源は分ける
- まずは前進、後退、左旋回、右旋回、停止だけを作る

## Project Layout

```text
buddy/
├── ai/
├── backend/
├── docs/
├── firmware/
├── hardware/
├── infra/
├── robot/
├── scripts/
└── web/
```
