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

Phase0: 開発環境構築

詳細手順: [docs/phase0.md](docs/phase0.md)

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
