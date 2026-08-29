# Phase4: ROS 2で機能を分割する

## Goal

既存のBuddyの機能を捨てず、モーター、距離、人物検出、追従判断、会話、安全監視を
独立したROS 2ノードへ段階的に分ける。最初はモーター制御だけをROS 2へ接続する。

## 移行方針

- 現行のCLIと`buddy-conversation.service`は、移行完了まで残す。
- GPIOへ触るプロセスは同時に1つだけにする。
- 各段階でモック確認を行い、その後に車輪を浮かせて実機確認する。
- ROS 2ノードは`robot/`の既存ロジックを再利用する。
- 新しい走行指令タイムアウトは追加しない。

最終的な構成は次を予定する。

```text
person_node -------- person target -----+
                                        +--> follow_node --> /cmd_vel --> motor_node
distance_node ------ range -------------+                       ^
                                                                |
conversation_node -- follow start/stop -------------------------+
power_node --------- safety stop -------------------------------+
```

## Step 0: Raspberry Piの環境を確認する

ROS 2の導入方法はOSで変わる。まだインストールせず、まず次の結果を記録する。

```sh
cat /etc/os-release
uname -m
python3 --version
df -h /
```

確認した実機環境は次のとおり。

```text
OS: Debian 13 (trixie)
Architecture: aarch64
Python: 3.13.5
Free storage: 101 GB
```

ROS 2 LyricalではDebian 13がTier 3、Python 3.12から3.14が対応範囲に含まれる。
完成済みバイナリは提供されないため、現在のSDカードを維持してLyricalをソースから
ビルドする。Jazzy向けUbuntuバイナリやUbuntu用APTリポジトリは追加しない。

## Step 0.5: ROS 2 Lyricalのビルドツールを準備する

まずDebian公式パッケージからビルドツールを導入する。

```sh
sudo apt update
sudo apt install -y \
  build-essential \
  cmake \
  git \
  colcon \
  python3-colcon-cmake \
  python3-colcon-python-setup-py \
  python3-colcon-ros \
  python3-pip \
  python3-pytest \
  python3-rosdep2 \
  vcstool
```

導入結果を確認する。

```sh
colcon --help | head
rosdep --version
vcs --version
```

この確認後に、ROS 2 Lyrical本体の取得、依存関係導入、ソースビルドへ進む。

## Step 1: motor_node

最初のノードは`buddy_robot`パッケージの`motor_node`。ROS 2標準の
`geometry_msgs/msg/Twist`を`/cmd_vel`で受け取り、既存の`BuddyDrive`へ渡す。

| 入力 | 単位 | 意味 |
| --- | --- | --- |
| `linear.x` | m/s | 正で前進、負で後退 |
| `angular.z` | rad/s | 正で左旋回、負で右旋回 |

そのほかのTwist成分は使用しない。既定の最高速度は仮の値であり、エンコーダーがないため
実速度を保証するものではない。実測後に`max_linear_speed`と`max_angular_speed`を調整する。

ROS 2を利用できる環境でワークスペースを用意する。

```sh
source ~/ros2_lyrical/install/local_setup.bash
mkdir -p ~/buddy_ros2_ws/src
ln -s ~/buddy ~/buddy_ros2_ws/src/buddy
cd ~/buddy_ros2_ws
colcon build --symlink-install --packages-select buddy_robot
source install/setup.bash
```

最初はGPIOを使用しないモックで起動する。

```sh
ros2 run buddy_robot motor_node --ros-args -p backend:=mock
```

別ターミナルでROS 2とワークスペースを読み込み、前進指令を1回送る。

```sh
source ~/ros2_lyrical/install/local_setup.bash
source ~/buddy_ros2_ws/install/setup.bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.3}, angular: {z: 0.0}}"
```

ノード側に次のようなログが出れば、ROS 2通信と速度変換は成功。

```text
cmd_vel left=0.35 right=0.35
```

停止指令は次のとおり。

```sh
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

## 実機確認前の注意

`backend:=gpiozero`は、ROS 2のモック確認とOS構成の確認が終わるまで使用しない。
実機では既存の会話サービスを停止し、車輪を浮かせ、モーター電池のスイッチへ手が届く
状態で行う。指令タイムアウトを設けていないため、ゼロ速度を送るか`motor_node`を終了する
まで最後の指令が維持される。

```sh
sudo systemctl stop buddy-conversation.service
```

## Phase4 Checklist

- [x] ROS 2パッケージの骨格を作成
- [x] `/cmd_vel`から左右モーター出力への変換を実装
- [x] ROS 2なしで速度変換を単体テスト
- [x] Raspberry PiのOSとアーキテクチャを確認
- [ ] ROS 2 Lyricalのビルドツールを導入
- [ ] ROS 2を導入
- [ ] `motor_node`をモックで起動
- [ ] 車輪を浮かせて`motor_node`を実機確認
- [ ] `distance_node`を追加
- [ ] `person_node`を追加
- [ ] `follow_node`を追加
- [ ] 会話・安全監視をROS 2へ接続

## References

- [ROS 2 Lyrical supported platforms](https://github.com/ros2/ros2_documentation/blob/rolling/source/Get-Started/Releases/lyrical/supported-platforms.rst)
- [ROS 2 source installation](https://docs.ros.org/en/rolling/Installation/Alternatives/Ubuntu-Development-Setup.html)
