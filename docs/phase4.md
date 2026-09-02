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
- 会話のドメイン状態はROS 2に依存させず、型付きイベントとして定義する。
- ROS 2への公開はアダプター層で行い、会話の単体テストにROS 2を必須にしない。

最終的な構成は次を予定する。

```text
person_node -------- person target -----+
                                        +--> follow_node --> /cmd_vel --> motor_node
distance_node ------ range -------------+                       ^
                                                                |
conversation_node -- follow start/stop -------------------------+
power_node --------- safety stop -------------------------------+
```

会話側は`ConversationEvent`として`waiting`、`listening`、`thinking`、
`speaking`、`stopped`のフェーズと、`calm`、`curious`、`warm`、
`confused`、`cautious`、`happy`のリアクションを保持する。現在はROS非依存の
状態遷移と通知境界を実装し、ROS 2アダプターが`/conversation/state`、
`/conversation/reaction`、`/conversation/event`へ配信する。QoSはReliable・Transient Local・
depth 1とし、後から起動する表示ノードでも最新状態を取得できる。現在は
`std_msgs/msg/String`を使うが、複数パッケージ構成へ移行する段階で専用interfaceパッケージの
カスタムmsgへ置き換える。

`reaction_node`は`/conversation/event`を購読し、表情、ライト色、ライトアニメーション、
効果音キューをまとめた`/reaction/command`を配信する。このノードは意味的な指示の変換だけを
担当し、GPIO、ディスプレイ、スピーカーを直接操作しない。機器ごとのドライバーノードは、
この指示を購読する構成で後から追加する。
現在の`reaction_output_node`は最初のドライバー実装で、表情を文字としてROSログへ表示する。
`ReactionOutputController`が同じ指示の重複適用を防ぎ、実機用ドライバーを追加するときも
ROS通信、状態変換、機器制御を分離したまま差し替えられる。

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

## Step 0.6: ROS 2 Lyricalのソースを取得する

Debianパッケージが用意したrosdep設定を更新する。

```sh
rosdep update
```

Lyricalの公式リポジトリ一覧からソースを取得する。

```sh
mkdir -p ~/ros2_lyrical/src
cd ~/ros2_lyrical
vcs import --input \
  https://raw.githubusercontent.com/ros2/ros2/lyrical/ros2.repos \
  src
```

主要リポジトリが取得できたことを確認する。

```sh
test -d ~/ros2_lyrical/src/ros2/rclpy && echo "rclpy=ok"
test -d ~/ros2_lyrical/src/ros2/common_interfaces && echo "interfaces=ok"
```

両方が`ok`なら、次は`rosdep install`でシステム依存関係を導入する。

## Step 0.7: ROS 2のシステム依存関係を導入する

取得済みのソースを除外し、Debian側で必要なライブラリを導入する。Connext DDSは
今回使用せず、ソースツリー内で解決する依存項目とともにスキップする。

```sh
cd ~/ros2_lyrical
rosdep install \
  --from-paths src \
  --ignore-src \
  --rosdistro lyrical \
  -y \
  --skip-keys "fastcdr rti-connext-dds-7.7.0 urdfdom_headers python3-vcstool"
```

最後に`All required rosdeps installed successfully`と表示されれば成功。Debian Tier 3では
未解決キーが見つかる可能性があるため、エラーが出た場合はキーをむやみにスキップせず、
その出力を確認してから対応する。

Debian 13では`python3-vcstool`というパッケージ名ではなく`vcstool`で提供される。
Step 0.5で`vcstool`を導入し、`vcs --version`が成功していることを確認したうえで、
rosdepキー`python3-vcstool`だけをスキップする。

## Step 0.8: ビルド前にCPUとメモリを確認する

Raspberry Piでのソースビルドは負荷が高いため、並列数を決める前に次を確認する。

```sh
nproc
free -h
swapon --show
```

メモリとスワップの合計に合わせて`colcon build`の並列数を決める。ビルド中も既存の
Buddyサービスを動かせるが、カメラ・音声処理とコンパイルが競合するため、ビルド開始前に
一時停止する。

確認した実機は4コア、RAM 4GB、zram 2GB。全パッケージの4並列ビルドは避け、Buddyの
最初のノードに必要なパッケージだけを、パッケージ単位では直列、CMakeでは最大2ジョブで
ビルドする。

## Step 0.9: ROS 2の最小構成をビルドする

SSH切断後もビルドを継続できるように`tmux`を導入し、既存のBuddyサービスを一時停止する。
この構成ではFast DDSを使う。専用SDKが必要なConnext DDS関連をcolconの探索から除外しておく。

```sh
sudo apt install -y tmux
sudo systemctl stop buddy-conversation.service
touch ~/ros2_lyrical/src/ros2/rmw_connextdds/COLCON_IGNORE
tmux new -s rosbuild
```

`colcon list | grep -i connext`が何も表示しなければ除外できている。

開いたtmux内で次を実行する。

```sh
cd ~/ros2_lyrical
export MAKEFLAGS=-j2
export CMAKE_BUILD_PARALLEL_LEVEL=2
colcon build \
  --symlink-install \
  --executor sequential \
  --packages-up-to \
    rclpy \
    geometry_msgs \
    ros2launch \
    ros2run \
    ros2service \
    ros2topic \
    rmw_fastrtps_cpp \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF
```

`Ctrl+B`に続けて`D`を押すと、ビルドを止めずにtmuxから離れられる。再接続する場合は
次を実行する。

```sh
tmux attach -t rosbuild
```

最後に`Summary: N packages finished`と表示され、failedがなければビルド成功。失敗した
場合は、再実行やファイル削除を行う前に、最初の`Failed <<< パッケージ名`とその直前の
エラーを確認する。

### エラーなしでビルドが中断した場合

プロセスが存在せず、ログ末尾が通常のCMakeコマンドで突然終わっている場合は、完了済みの
パッケージを残したまま再開する。`nohup`を使い、SSH切断後も処理を継続する。

```sh
cd ~/ros2_lyrical
nohup env \
  MAKEFLAGS=-j2 \
  CMAKE_BUILD_PARALLEL_LEVEL=2 \
  colcon build \
    --symlink-install \
    --executor sequential \
    --packages-skip-build-finished \
    --packages-up-to \
      rclpy \
      geometry_msgs \
      ros2launch \
      ros2run \
      ros2service \
      ros2topic \
      rmw_fastrtps_cpp \
    --cmake-args \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_TESTING=OFF \
  > ~/ros2_lyrical/rosbuild-resume.log 2>&1 &
echo $!
```

進行状況は次で確認する。

```sh
pgrep -af colcon
tail -f ~/ros2_lyrical/rosbuild-resume.log
```

`tail -f`だけを終了する場合は`Ctrl+C`を押す。colcon本体は停止しない。再起動や電源断を
行うと`nohup`でも停止するため、ビルド完了までRaspberry Piの電源を維持する。

### 中断後に0バイトのCMake生成ファイルが残った場合

中断されたパッケージの`install/<package>`に0バイトの`*Export.cmake`が残ると、
後続パッケージがエクスポート先を読み込めず失敗する。該当パッケージの`build`と
`install`だけをワークスペース外へ退避し、`--packages-skip-build-finished`付きで再開する。
退避先を`~/ros2_lyrical`内に作るとcolconがパッケージを重複検出するため、必ず外側に置く。

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

初回ビルド後は、ROS 2本体、Buddyオーバーレイ、既存の`.venv`をまとめて読み込める。
VL53L1Xなど`.venv`内のPythonパッケージも、ROS 2ノードから利用できる。

```sh
source ~/buddy/scripts/source_ros2.sh
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

## Step 2: distance_node

`distance_node`は既存の`DistanceSensor`層を再利用し、前方距離をROS 2標準の
`sensor_msgs/msg/Range`で`/distance/front`へ配信する。既存ドライバーのcmをROS標準のmへ
変換する。先にROS 2本体の`sensor_msgs`を追加ビルドする。

```sh
source ~/ros2_lyrical/install/local_setup.bash
cd ~/ros2_lyrical
colcon build \
  --symlink-install \
  --executor sequential \
  --packages-skip-build-finished \
  --packages-up-to sensor_msgs \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF
```

Buddy側のオーバーレイを再ビルドする。

```sh
source ~/ros2_lyrical/install/local_setup.bash
cd ~/buddy_ros2_ws
colcon build --symlink-install --packages-select buddy_robot
source install/setup.bash
```

まずはI2Cを使わないモックで起動する。

```sh
ros2 run buddy_robot distance_node --ros-args \
  -p backend:=mock \
  -p mock_distance_cm:=123.4
```

別ターミナルでトピックを1回受信する。`range: 1.234`前後が表示されれば、
通信と単位変換は成功。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 topic echo --once /distance/front sensor_msgs/msg/Range
```

モック確認後にVL53L1Xへ切り替える。

```sh
ros2 run buddy_robot distance_node --ros-args \
  -p backend:=vl53l1x \
  -p distance_mode:=2 \
  -p timing_budget_ms:=100
```

## Step 3: person_node

`person_node`はカメラと人物検出器だけを所有し、安定化した人物位置を
`/person/target`へ配信する。モーターや距離センサーには触れない。カスタムROSメッセージを
別パッケージ化するまでは、検出の全フィールドを1件のJSONにして`std_msgs/msg/String`で送る。

Buddyオーバーレイを再ビルドし、まずカメラを使わないモックで起動する。

```sh
source ~/buddy/scripts/source_ros2.sh
cd ~/buddy_ros2_ws
colcon build --symlink-install --packages-select buddy_robot
source install/setup.bash

ros2 run buddy_robot person_node --ros-args \
  -p backend:=mock \
  -p mock_position:=right
```

別ターミナルでメッセージを1回受信する。`detected`が`true`、`position`が`right`なら
通信とターゲット変換は成功。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 topic echo --once /person/target std_msgs/msg/String --field data
```

モック確認後に、現行CLIで実績のあるMediaPipeモデルへ切り替える。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 run buddy_robot person_node --ros-args \
  -p backend:=mediapipe \
  -p fps:=5.0
```

## Step 4: follow_node

`follow_node`は`/person/target`と`/distance/front`を組み合わせ、判断結果を`/cmd_vel`へ
配信する。GPIOには触れず、既定では追従無効。`/follow/enable`サービスで明示的に
開始する。人物入力が古い場合は停止し、距離入力がない場合は前進せず左右のその場旋回だけを
許可する。

実機モーターに触れない統合確認では、4つのノードを別ターミナルで起動する。

```sh
# terminal 1
source ~/buddy/scripts/source_ros2.sh
ros2 run buddy_robot motor_node --ros-args -p backend:=mock
```

```sh
# terminal 2
source ~/buddy/scripts/source_ros2.sh
ros2 run buddy_robot distance_node --ros-args \
  -p backend:=mock -p mock_distance_cm:=200.0
```

```sh
# terminal 3
source ~/buddy/scripts/source_ros2.sh
ros2 run buddy_robot person_node --ros-args \
  -p backend:=mock -p mock_position:=center
```

```sh
# terminal 4
source ~/buddy/scripts/source_ros2.sh
ros2 run buddy_robot follow_node
```

最後のターミナルから追従を開始する。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 service call /follow/enable std_srvs/srv/SetBool "{data: true}"
```

`motor_node`に`cmd_vel left=0.35 right=0.35`が出れば、人物・距離・判断・モーター変換の
経路が接続できている。終了時は無効化を先に送る。

```sh
ros2 service call /follow/enable std_srvs/srv/SetBool "{data: false}"
```

## Step 5: 走行と電源監視ノードをlaunchでまとめる

`buddy_follow.launch.py`で、motor・distance・person・follow・powerの5ノードを1コマンドで
起動する。既定は全バックエンドがモック、電源正常、追従無効のため車輪は動かない。

ROS 2本体に`ros2 launch`コマンドがない場合は追加ビルドする。

```sh
source ~/ros2_lyrical/install/local_setup.bash
cd ~/ros2_lyrical
colcon build \
  --symlink-install \
  --executor sequential \
  --packages-skip-build-finished \
  --packages-up-to ros2launch \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF
```

モック結合は次の1コマンドで起動できる。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 launch buddy_robot buddy_follow.launch.py
```

実機では車輪を浮かせ、既存サービスを停止してから、3つのバックエンドを明示する。

```sh
sudo systemctl stop buddy-conversation.service
source ~/buddy/scripts/source_ros2.sh
ros2 launch buddy_robot buddy_follow.launch.py \
  motor_backend:=gpiozero \
  distance_backend:=vl53l1x \
  person_backend:=mediapipe \
  power_backend:=raspberry_pi \
  max_speed:=1.0
```

起動後も追従は無効。別ターミナルから`/follow/enable`を`true`にして開始する。
電源が低電圧の間、監視できない間、または電源メッセージが途絶した場合は追従を停止する。

実機前に低電圧停止をモックで確認できる。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 launch buddy_robot buddy_follow.launch.py mock_power_good:=false
```

追従を有効化しても`follow_node`が`reason=power-low`の停止を維持すれば成功。

## Step 6: 会話からROS 2追従を操作する

会話ループの`--mobility-backend ros2-follow`は、従来の人物追従CLIを別プロセス起動せず、
ROS 2の`/follow/enable`サービスを呼ぶ。「ねえバディ」で会話開始後、従来と同じ音声指示で
追従を開始・停止できる。「バイバイ」や音声割り込み停止も同じサービス経由で停止する。
会話プロセスが予期せず終了した場合も、systemdの`ExecStopPost`が追従無効化を送る。

systemdは2サービスに分ける。`buddy-ros-follow.service`が実カメラ、距離、電源、モーター、
追従判断を追従無効で待機させ、`buddy-conversation.service`が音声対話と開始・停止指示を担当する。
手動で起動した`ros2 launch`や旧会話サービスが動いているとカメラ・GPIOが競合するため、
インストール前に手動launchを`Ctrl+C`で終了する。

```sh
cd ~/buddy
bash scripts/install_buddy_service.sh
```

導入後は両サービスと追従待機状態を確認する。

```sh
systemctl --no-pager --full status buddy-ros-follow.service
systemctl --no-pager --full status buddy-conversation.service
source ~/buddy/scripts/source_ros2.sh
ros2 topic echo --once /follow/status std_msgs/msg/String --field data
```

起動直後が`enabled=false`なら安全な待機状態。実車確認は車輪を浮かせ、モーター電池を
すぐ切れる状態で行う。

ROS 2の`local_setup.bash`は未設定変数を内部で使うため、これを読むsystemdラッパーで
`set -u`を有効にしない。`COLCON_CURRENT_PREFIX: unbound variable`が出る場合はラッパーが古い。
`source_ros2.sh`は呼び出し元シェルの変数を消さないよう、内部変数を`buddy_ros2_env_`で名前空間化する。

## Phase4 Checklist

- [x] ROS 2パッケージの骨格を作成
- [x] `/cmd_vel`から左右モーター出力への変換を実装
- [x] ROS 2なしで速度変換を単体テスト
- [x] Raspberry PiのOSとアーキテクチャを確認
- [x] ROS 2 Lyricalのビルドツールを導入
- [x] ROS 2 Lyricalのソースを取得
- [x] ROS 2のシステム依存関係を導入
- [x] CPU・メモリ・スワップを確認
- [x] ROS 2 Lyricalの最小構成をビルド
- [x] ROS 2を導入
- [x] `motor_node`をモックで起動
- [x] 車輪を浮かせて`motor_node`を実機確認
- [x] `distance_node`を追加
- [x] `person_node`を追加
- [x] `follow_node`を追加
- [x] 4ノードをモックで結合テスト
- [x] 実カメラ・実距離センサー・実モーターで人物追従を結合テスト
- [x] `power_node`を追加し、追従判断にフェイルセーフ接続
- [x] mock低電圧とRaspberry Pi実電源正常時の追従判断を確認
- [x] 会話からROS 2追従を操作するバックエンドを実装
- [x] systemdのROS 2待機と音声開始・停止を実機確認
- [x] 会話状態とリアクションをROS 2へ配信

## References

- [ROS 2 Lyrical supported platforms](https://github.com/ros2/ros2_documentation/blob/rolling/source/Get-Started/Releases/lyrical/supported-platforms.rst)
- [ROS 2 source installation](https://docs.ros.org/en/rolling/Installation/Alternatives/Ubuntu-Development-Setup.html)
