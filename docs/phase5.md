# Phase5: 自律走行

## Goal

Buddyの車体座標系、自己位置、周辺地図をROS 2で扱い、最終的にNav2から安全に
目的地へ移動できるようにする。

## Step 1: URDFとTF

最初に追加部品を使わず、車体・車輪・キャスター・カメラ・正面距離センサーの位置関係を
`urdf/buddy.urdf.xacro`へ定義する。座標系はREP-105に合わせ、前をx正、左をy正、上をz正とする。

```text
base_footprint
└── base_link
    ├── left_wheel_link
    ├── right_wheel_link
    ├── caster_link
    ├── camera_link
    │   └── camera_optical_frame
    └── front_distance_sensor_link
```

2026-08-31に実機寸法を測定し、launch引数の既定値へ反映した。`base_link`は左右タイヤの
軸中央に置き、床面上の投影を`base_footprint`とする。

| 項目 | 実測値 |
| --- | ---: |
| タイヤ直径 | 7 cm |
| タイヤ幅 | 3 cm |
| 左右タイヤ中心間 | 10 cm |
| タイヤ軸から車体前端 | +8 cm |
| タイヤ軸から車体後端 | -14 cm |
| 床からカメラレンズ中央 | 14 cm |
| タイヤ軸からカメラレンズ | +8 cm |
| 床から距離センサー中央 | 5 cm |
| タイヤ軸から距離センサー | +8 cm |
| タイヤ軸からキャスター中心 | -12 cm |

車体幅と車体高さは未実測のため、それぞれ10 cmと6 cmの仮値を使用する。

Raspberry PiのROS 2ワークスペースで必要なパッケージを追加ビルドする。

```sh
source ~/ros2_lyrical/install/local_setup.bash
cd ~/ros2_lyrical

MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build \
  --symlink-install \
  --executor sequential \
  --packages-skip-build-finished \
  --packages-up-to xacro robot_state_publisher \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF
```

Buddyパッケージを再ビルドする。

```sh
source ~/ros2_lyrical/install/local_setup.bash
cd ~/buddy_ros2_ws
colcon build --symlink-install --packages-select buddy_robot
source install/setup.bash
```

URDFを起動する。

```sh
ros2 launch buddy_robot buddy_description.launch.py
```

別ターミナルでTFを確認する。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 topic echo --once /tf_static
```

`base_link`から`camera_link`と`front_distance_sensor_link`への変換が出ればStep 1の
通信は成功。距離ノードの`Range.header.frame_id`も
`front_distance_sensor_link`へ統一する。

## Step 2: オープンループ・オドメトリ

実エンコーダーを導入する前に、`odometry_node`が`/cmd_vel`を積分して仮の自己位置を
`/odom`へ配信する。あわせて`odom -> base_footprint`の動的TFを配信する。

この値は指令速度だけから計算するため、タイヤの滑り、モーター差、キャスターの向き、
衝突による停止を検出できない。ROS 2通信を確認するための暫定値であり、SLAMや実際の
自律走行ではエンコーダーとIMUを使う実測オドメトリへ置き換える。

Buddyパッケージを再ビルドした後、モーター電池をOFFにして起動する。

```sh
source ~/buddy/scripts/source_ros2.sh
ros2 launch buddy_robot buddy_odometry.launch.py
```

別ターミナルから2秒間、前進速度だけを送る。このlaunchには`motor_node`が含まれないため、
車輪は動かない。

```sh
source ~/buddy/scripts/source_ros2.sh
timeout 2 ros2 topic pub --rate 10 \
  /cmd_vel \
  geometry_msgs/msg/Twist \
  "{linear: {x: 0.1}, angular: {z: 0.0}}"
```

自己位置とTFを確認する。

```sh
ros2 topic echo --once /odom nav_msgs/msg/Odometry
ros2 topic echo --once /tf tf2_msgs/msg/TFMessage
```

`/odom`の`pose.pose.position.x`が約0.2 mになり、`odom`から`base_footprint`へのTFが
出れば成功。指令が0.5秒途絶えると積分を停止する。原点へ戻す場合は次を実行する。

```sh
ros2 service call /odom/reset std_srvs/srv/Empty "{}"
```

## 次のStep

エンコーダーの機種決定前でも検証できるよう、`odometry_control.py`には累積tickを受け取る
ハードウェア非依存の差動二輪オドメトリを用意している。部品到着後はタイヤ1回転あたりの
tick数を確認し、GPIOまたは専用コントローラーから左右の累積tickを渡す入力層を追加する。
既定値は設けず、実測したタイヤ径、左右タイヤ中心間、tick数を明示的に設定する。

数値センサーイベントだけをJSON Linesへ保存すると、実機を動かさず追従判断と
エンコーダーオドメトリを再生できる。録音や画像はシナリオへ含めない。

```sh
python3 -m robot.scenario_cli scenario.jsonl \
  --wheel-diameter 0.07 \
  --wheel-separation 0.10 \
  --ticks-per-revolution 20
```

イベントの`type`には`enable`、`person`、`distance`、`power`、`encoder`、`sample`を
指定する。タイヤ径、左右タイヤ中心間、tick数には部品到着後の実測値を使用する。

1. エンコーダーとIMUの構成を決める
2. `/joint_states`と実測オドメトリを実装する
3. 2D LiDARを追加する
4. SLAMで地図を作成する
5. Nav2で自律移動する

## Phase5 Checklist

- [x] URDF/Xacroの骨格を作成
- [x] `base_footprint`を起点とした車体座標系を定義
- [x] 距離メッセージのフレーム名をURDFへ統一
- [x] `robot_state_publisher`をRaspberry Piへ導入
- [x] `/tf_static`を実機で確認
- [x] 車体寸法を実測して反映（車体幅・高さを除く）
- [x] `/cmd_vel`を使うオープンループ`/odom`を実装
- [x] オープンループ`/odom`と動的TFを実機で確認
- [ ] オドメトリ用ハードウェアを決定
- [ ] エンコーダーとIMUを使う実測`/odom`を実装
- [ ] 2D LiDARを接続
- [ ] SLAMで地図を保存
- [ ] Nav2で自律移動
