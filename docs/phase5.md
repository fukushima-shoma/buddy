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

## 次のStep

1. 実測寸法をURDFへ反映する
2. エンコーダーとIMUの構成を決める
3. `/joint_states`、`/odom`、`odom -> base_footprint`を実装する
4. 2D LiDARを追加する
5. SLAMで地図を作成する
6. Nav2で自律移動する

## Phase5 Checklist

- [x] URDF/Xacroの骨格を作成
- [x] `base_footprint`を起点とした車体座標系を定義
- [x] 距離メッセージのフレーム名をURDFへ統一
- [x] `robot_state_publisher`をRaspberry Piへ導入
- [x] `/tf_static`を実機で確認
- [x] 車体寸法を実測して反映（車体幅・高さを除く）
- [ ] オドメトリ用ハードウェアを決定
- [ ] `/odom`を実装
- [ ] 2D LiDARを接続
- [ ] SLAMで地図を保存
- [ ] Nav2で自律移動
