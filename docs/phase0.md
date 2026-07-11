# Phase0: 開発環境構築

## Goal

Raspberry PiへSSH接続し、VS Codeから編集でき、Pythonを実行できる状態を作る。

Phase0ではMac側にDocker Desktopを入れる。Raspberry PiへのDocker導入は、Web画面やクラウド連携を始めるPhase6以降に回す。

## Step 1: GitHubリポジトリ作成

GitHubで `buddy` リポジトリを作る。

完了条件:

- GitHub上に `buddy` が存在する
- READMEをPushできる

## Step 2: Macの開発環境

インストールするもの:

- VS Code
- Docker Desktop
- Raspberry Pi Imager
- Git
- Python 3

確認コマンド:

```sh
git --version
python3 --version
docker --version
```

完了条件:

- すべてのコマンドが正常終了する

## Step 3: Raspberry Piセットアップ

Raspberry Pi Imagerで以下を設定する。

- OS: Raspberry Pi OS Lite 64-bit
- Hostname: `buddy`
- SSH: ON
- Wi-Fi: 使用するネットワークを設定
- User: `pi`

完了条件:

- Raspberry Piが起動する
- 同じネットワーク上で `buddy.local` として見える

## Step 4: SSH接続

Macから接続する。

```sh
ssh pi@buddy.local
```

完了条件:

- SSHログインできる

## Step 5: Linux更新

Raspberry Pi上で実行する。

```sh
sudo apt update
sudo apt upgrade
sudo reboot
```

完了条件:

- パッケージ更新後に再起動できる
- 再起動後もSSH接続できる

## Step 6: Git設定

Raspberry Pi上でGitのユーザー情報を設定する。

```sh
git config --global user.name "あなたの名前"
git config --global user.email "メールアドレス"
```

SSHキーを作成する。

```sh
ssh-keygen
```

公開鍵をGitHubへ登録する。

完了条件:

- Raspberry PiからGitHubへPushできる

## Step 7: VS Code Remote SSH

MacのVS CodeにRemote SSH拡張を入れ、`buddy.local` に接続する。

完了条件:

- VS CodeからRaspberry Pi上のファイルを編集できる

## Step 8: Python確認

Raspberry Pi上で `hello.py` を作る。

```py
print("Hello Buddy")
```

実行する。

```sh
python3 hello.py
```

完了条件:

- `Hello Buddy` が表示される

## Step 9: プロジェクト構成作成

このリポジトリに以下の構成を作る。

```text
buddy/
├── docs/
├── hardware/
├── firmware/
├── robot/
├── ai/
├── backend/
├── web/
├── infra/
└── scripts/
```

完了条件:

- ディレクトリがGitHubへPushされる

## Phase0完了チェックリスト

| 項目 | 状態 |
| --- | --- |
| GitHub作成 | ☑ |
| Mac開発環境 | ☑ |
| Raspberry Pi起動 | ☑ |
| SSH接続 | ☑ |
| Linux更新 | ☑ |
| Git設定 | ☑ |
| VS Code接続 | ☑ |
| Python実行 | ☑ |
| ディレクトリ作成 | ☑ |
| README作成 | ☑ |

## Phase0で完成する状態

```text
Mac
├── VS Code
├── Docker Desktop
├── Git
└── SSH
    └── Raspberry Pi
        ├── Python
        ├── Git
        └── Buddy Project
```
