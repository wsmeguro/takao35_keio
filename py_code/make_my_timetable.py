import os
import json
import csv
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class StationInfo:
    name: str
    use_type: str   # deperture, transit, destination
    departuret_time: Optional[str] = None
    deptarture_platform: Optional[int] = None
    arrival_time: Optional[str] = None
    arrival_platform: Optional[int] = None

@dataclass
class RouteInfo:
    train_type: str  # Keio_Liner, Express, Local
    origin_station_info: StationInfo
    terminal_station_info: StationInfo
    transits: Optional[List[StationInfo]] = None

def parse_json(json_string):
    try:
        return json.loads(json_string)
    except (TypeError, json.JSONDecodeError):
        return None  # または適切なエラーハンドリング

today_str = datetime.now().strftime("%Y%m%d")
day_type = ["weekday", "holiday"]
data_dir = os.path.join(os.path.dirname(__file__), "..", "py_data", "keio")
output_dir = os.path.join(os.path.dirname(__file__), "..", "py_data", "output")

def get_next_train_kitano_to_takao(target_time: str, d_type) -> Optional[Dict]:
    fk_name = f"{today_str}_{d_type}_kitano_to_takao.csv"
    fk_path = os.path.join(data_dir, fk_name)
    df_k = pd.read_csv(fk_path)
    dp_time = None
    ar_time = None
    for index, row in df_k.iterrows():
        if row['time_iso'] >= target_time:
            tmp_d_time = row['time_iso']
            stop_stations: List[Dict] = row['stop_stations']
            for st in stop_stations:
                if st['station'] == "高尾山口":
                    tmp_a_time = st['time']
                
                if ar_time is None or tmp_a_time < ar_time:
                    dp_time = tmp_d_time
                    ar_time = tmp_a_time
                    result = {
                        "departure_time": dp_time,
                        "arrival_time": ar_time,
                        "train_type": row['train_type'],
                        "operation_id": row['operation_id'],
                        "platform": row['platform'],
                    }

    return result

def get_next_train_kitano_to_shinjuku(target_time: str, d_type) -> Optional[Dict]:
    fk_name = f"{today_str}_{d_type}_kitano_to_shinjuku.csv"
    fk_path = os.path.join(data_dir, fk_name)
    df_k = pd.read_csv(fk_path)
    dp_time = None
    ar_time = None
    for index, row in df_k.iterrows():
        if row['time_iso'] >= target_time:
            tmp_d_time = row['time_iso']
            stop_stations: List[Dict] = row['stop_stations']
            for st in stop_stations:
                if st['station'] == "高尾山口":
                    tmp_a_time = st['time']
                
                if ar_time is None or tmp_a_time < ar_time:
                    dp_time = tmp_d_time
                    ar_time = tmp_a_time
                    result = {
                        "departure_time": dp_time,
                        "arrival_time": ar_time,
                        "train_type": row['train_type'],
                        "operation_id": row['operation_id'],
                        "platform": row['platform'],
                    }

    return result

def station_info_from_dict(data: dict) -> StationInfo:
    return StationInfo(**data)

def shinjuku_to_takao3():
    all_routes = []
    # direct
    for d_type in day_type:
        fs_name = f"{today_str}_{d_type}_shinjuku_to_takao_direct.csv"
        fs_path = os.path.join(data_dir, fs_name)

        if os.path.exists(fs_path) is False:
            continue
        df_s = pd.read_csv(fs_path)
        if df_s.empty:
            continue
        df_s['stop_stations'] = df_s['stop_stations'].apply(parse_json)
        if os.path.exists(fk_path) is False:
            continue

        for index, row in df_s.iterrows():
            # hour,minute,operation_id,train_type,destination,platform,departure_dt,time_iso,stop_stations
            # 6,51,80040000,特急,高尾山口,１,06:51,2025-08-24T06:51:00+09:00,"[{""station"": ""新宿"", ""time"": ""2025-08-24T06:10:00+09:00""}, {""station"": ""笹塚"", ""time"": ""2025-08-24T06:15:00+09:00""}, {""station"": ""明大前"", ""time"": ""2025-08-24T06:17:00+09:00""}, {""station"": ""千歳烏山"", ""time"": ""2025-08-24T06:22:00+09:00""}, {""station"": ""調布"", ""time"": ""2025-08-24T06:29:00+09:00""}, {""station"": ""府中"", ""time"": ""2025-08-24T06:36:00+09:00""}, {""station"": ""分倍河原"", ""time"": ""2025-08-24T06:38:00+09:00""}, {""station"": ""聖蹟桜ヶ丘"", ""time"": ""2025-08-24T06:41:00+09:00""}, {""station"": ""高幡不動"", ""time"": ""2025-08-24T06:45:00+09:00""}, {""station"": ""北野"", ""time"": ""2025-08-24T06:51:00+09:00""}, {""station"": ""京王片倉"", ""time"": ""2025-08-24T06:53:00+09:00""}, {""station"": ""山田"", ""time"": ""2025-08-24T06:55:00+09:00""}, {""station"": ""めじろ台"", ""time"": ""2025-08-24T06:57:00+09:00""}, {""station"": ""狭間"", ""time"": ""2025-08-24T06:59:00+09:00""}, {""station"": ""高尾"", ""time"": ""2025-08-24T07:01:00+09:00""}, {""station"": ""高尾山口"", ""time"": ""2025-08-24T07:04:00+09:00""}]"
            origin = StationInfo(
                name="新宿",
                use_type="deperture",
                departuret_time=row['departure_time'],  # DataFrameから取得
                deptarture_platform=row['departure_platform'],  # DataFrameから取得
            )
            stop_stations: List[Dict] = row['stop_stations']  # 型ヒントを追加
            for st in stop_stations:
                if st['station'] == "高尾山口":
                    a_time = st['time']
                else:
                    a_time = None
            terminal = StationInfo(
                name="高尾山口",
                use_type="destination",
                arrival_time=a_time,  # 高尾到着時間
            )
            transit_info = None

            route_info = RouteInfo(
                train_type=row['train_type'],  # DataFrameから取得
                origin_station_info=origin,
                terminal_station_info=terminal,
                transits=transit_info  # 高尾山口行きは途中駅情報なし
            )
            all_routes.append(route_info)

        fk_name = f"{today_str}_{day_type[0]}_shinjuku_to_keiohachioji.csv"
        fk_path = os.path.join(data_dir, fk_name)
        df_k = pd.read_csv(fk_path)
        if df_k.empty:
            continue
        df_k['stop_stations'] = df_k['stop_stations'].apply(parse_json)
            # hour,minute,operation_id,train_type,destination,platform,departure_dt,time_iso,stop_stations
            # 6,51,80040000,特急,高尾山口,１,06:51,2025-08-24T06:51:00+09:00,"[{""station"": ""新宿"", ""time"": ""2025-08-24T06:10:00+09:00""}, {""station"": ""笹塚"", ""time"": ""2025-08-24T06:15:00+09:00""}, {""station"": ""明大前"", ""time"": ""2025-08-24T06:17:00+09:00""}, {""station"": ""千歳烏山"", ""time"": ""2025-08-24T06:22:00+09:00""}, {""station"": ""調布"", ""time"": ""2025-08-24T06:29:00+09:00""}, {""station"": ""府中"", ""time"": ""2025-08-24T06:36:00+09:00""}, {""station"": ""分倍河原"", ""time"": ""2025-08-24T06:38:00+09:00""}, {""station"": ""聖蹟桜ヶ丘"", ""time"": ""2025-08-24T06:41:00+09:00""}, {""station"": ""高幡不動"", ""time"": ""2025-08-24T06:45:00+09:00""}, {""station"": ""北野"", ""time"": ""2025-08-24T06:51:00+09:00""}, {""station"": ""京王片倉"", ""time"": ""2025-08-24T06:53:00+09:00""}, {""station"": ""山田"", ""time"": ""2025-08-24T06:55:00+09:00""}, {""station"": ""めじろ台"", ""time"": ""2025-08-24T06:57:00+09:00""}, {""station"": ""狭間"", ""time"": ""2025-08-24T06:59:00+09:00""}, {""station"": ""高尾"", ""time"": ""2025-08-24T07:01:00+09:00""}, {""station"": ""高尾山口"", ""time"": ""2025-08-24T07:04:00+09:00""}]"
        for index, row in df_k.iterrows():
            origin = StationInfo(
                name="新宿",
                use_type="deperture",
                departuret_time=row['departure_time'],  # DataFrameから取得
                deptarture_platform=row['departure_platform'],  # DataFrameから取得
            )
            stop_stations: List[Dict] = row['stop_stations']  # 型ヒントを追加
            for st in stop_stations:
                if st['station'] == "北野":
                    a_time = st['time']
                else:
                    a_time = None
            if a_time:
                :
            transit_info = StationInfo(
                name="北野",
                use_type="destination",
                arrival_time=a_time,  # 高尾到着時間
            )
            # stop_stationsカラムからtransit情報を生成
            transits_data = row.get('stop_stations')
            transits = None
            if transits_data:
                transits = [station_info_from_dict(s) for s in transits_data]

            route_info = RouteInfo(
                route_type=row['route_type'],  # DataFrameから取得
                origin_station_info=origin,
                terminal_station_info=terminal,
                transits=transits
            )
            all_routes.append(route_info)

    # JSONファイルに保存
    output_file = os.path.join(output_dir, f"{today_str}_all_routes.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([route.__dict__ for route in all_routes], f, ensure_ascii=False, indent=4, default=str)  # dataclassをdictに変換してJSON出力

    print(f"データは {output_file} に保存されました。")

# 実行例
shinjuku_to_takao3()