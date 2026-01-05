import sys
import json
from pathlib import Path
import pandas as pd
from fitparse import FitFile
from datetime import timedelta
import matplotlib.pyplot as plt
import numpy as np
import os # Importation nécessaire

# La commande a lancer : python extract_fit_file.py "./uploads/fichier.fit" ./results/

# Facteur de conversion de la vitesse: 1 m/s = 3.6 km/h
MS_TO_KMH = 3.6

# Seuil pour la détection des arrêts longs et immobiles
PAUSE_TIME_THRESHOLD_S = 10.0
PAUSE_DISTANCE_THRESHOLD_M = 1.0

# Nouveaux seuils de vitesse pour la classification des laps
INTENSITY_SPEED_THRESHOLD = 17.05
RECOVERY_SPEED_THRESHOLD = 8.65

def format_seconds_to_min_sec(seconds):
    if pd.isna(seconds):
        return None
    total_seconds = int(seconds)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def classify_lap_nature_by_speed(df_laps):
    """
    Classifie la nature des laps (Warm-up, Intensity, Recovery, Cool-down)
    en se basant sur avg_speed_kmh, avec une logique séquentielle.
    """
    
    if df_laps.empty or 'avg_speed_kmh' not in df_laps.columns:
        if 'lap_nature' not in df_laps.columns:
            df_laps['lap_nature'] = 'Unknown'
        return df_laps
        
    df_laps['lap_nature'] = 'Unknown'
    
    # 1. Intensité : Vitesse > 17.05 km/h
    mask_intensity = (df_laps['avg_speed_kmh'] > INTENSITY_SPEED_THRESHOLD)
    df_laps.loc[mask_intensity, 'lap_nature'] = 'Intensity'

    # Identifier les bornes (index) des laps d'Intensité
    intensity_laps = df_laps[df_laps['lap_nature'] == 'Intensity']
    
    if not intensity_laps.empty:
        first_intensity_idx = intensity_laps.index.min()
        last_intensity_idx = intensity_laps.index.max()
        
        # 2. Warm-up : Tous les laps AVANT le premier lap d'Intensité
        mask_warm_up = (df_laps.index < first_intensity_idx) & \
                       (df_laps['avg_speed_kmh'].between(RECOVERY_SPEED_THRESHOLD, INTENSITY_SPEED_THRESHOLD, inclusive='both'))
        df_laps.loc[mask_warm_up, 'lap_nature'] = 'Warm-up'
        
        # 3. Cool-down : Tous les laps APRÈS le dernier lap d'Intensité
        mask_cool_down = (df_laps.index > last_intensity_idx) & \
                         (df_laps['avg_speed_kmh'].between(RECOVERY_SPEED_THRESHOLD, INTENSITY_SPEED_THRESHOLD, inclusive='both'))
        df_laps.loc[mask_cool_down, 'lap_nature'] = 'Cool-down'
        
        # 4. Recovery : Basse vitesse (< 8.65) ET suit un lap d'Intensité (logique séquentielle)
        
        # Colonne temporaire pour la nature du lap précédent
        df_laps['prev_lap_nature'] = df_laps['lap_nature'].shift(1)
        
        mask_low_speed = (df_laps['avg_speed_kmh'] < RECOVERY_SPEED_THRESHOLD)
        
        # Un lap de Recovery doit être lent ET suivre un lap classé Intensity
        # On inclut ici les laps de Recovery qui n'ont pas encore été classifiés
        mask_recovery = mask_low_speed & (df_laps['prev_lap_nature'] == 'Intensity')
        df_laps.loc[mask_recovery, 'lap_nature'] = 'Recovery'
        
        # 5. Classer le reste entre les bornes (les laps 'Unknown' restants dans le bloc de travail)
        mask_remaining_unknown = (df_laps.index >= first_intensity_idx) & \
                                 (df_laps.index <= last_intensity_idx) & \
                                 (df_laps['lap_nature'] == 'Unknown')
                                 
        df_laps.loc[mask_remaining_unknown, 'lap_nature'] = 'Recovery'

        df_laps = df_laps.drop(columns=['prev_lap_nature'], errors='ignore')

    else:
        # S'il n'y a pas de lap d'Intensité détecté
        df_laps.loc[df_laps['lap_nature'] == 'Unknown', 'lap_nature'] = 'Warm-up'
        
    return df_laps

def parse_fit(ff):
    # 1. Extraction des enregistrements de la session (Record Messages)
    rows = []
    columns_to_drop = [
        "activity_type", "enhanced_altitude", "enhanced_speed", "fractional_cadence", 
        "unknown_87", "unknown_88", "unknown_90", "speed", "cadence", "position_lat", "position_long"
    ]
    
    for rec in ff.get_messages('record'):
        r = {}
        for field in rec:
            r[field.name] = field.value
        rows.append(r) 
        
    if not rows:
        raise RuntimeError("Aucun record trouvé dans le fichier .fit")
    
    df = pd.DataFrame(rows)
    
    # 2. Nettoyage et normalisation des données
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['elapsed_time_s'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds()
    
    # 3. Conversion de la vitesse m/s -> km/h
    if 'speed' in df.columns:
        df['speed_kmh'] = np.round(df['speed'] * MS_TO_KMH, 2)
        
    # 4. Traitements sur les colonnes existantes
    if 'cadence' in df.columns:
        df['cadence_step_per_min'] = df['cadence'] * 2

    for col in ['stance_time', 'step_length', 'altitude']:
        if col in df.columns:
            df[col] = np.round(df[col]).astype('Int64')

    # 5. Ajout de l'information des laps
    df = add_lap_info(ff, df) # Appel à la fonction modifiée
    
    # 6. Ajout du temps écoulé dans le lap en cours (elapsed_time_in_lap_s)
    if 'lap_number' in df.columns and 'elapsed_time_s' in df.columns:
        lap_start_time = df.groupby('lap_number')['elapsed_time_s'].transform('min')
        df['elapsed_time_in_lap_s'] = df['elapsed_time_s'] - lap_start_time
        df['elapsed_time_in_lap_s'] = np.round(df['elapsed_time_in_lap_s'], 1)

    # 7. Ajout des colonnes demandées (Moving Time)
    if 'elapsed_time_s' in df.columns and 'distance' in df.columns:
        df['dt'] = df['elapsed_time_s'].diff()
        df['dd'] = df['distance'].diff().fillna(0)
        
        is_break_real = (df['dt'] >= PAUSE_TIME_THRESHOLD_S) & (df['dd'] <= PAUSE_DISTANCE_THRESHOLD_M)
        
        df['pause_correction_s'] = np.where(is_break_real, df['dt'] - 1.0, 0.0)
        df.loc[0, 'pause_correction_s'] = 0.0
        
        df['cumulative_pause_s'] = df['pause_correction_s'].cumsum()
        
        df['moving_elapsed_time_s'] = df['elapsed_time_s'] - df['cumulative_pause_s']
        df['moving_elapsed_time_s'] = np.round(df['moving_elapsed_time_s'], 1)
        
        df = df.drop(columns=['dt', 'dd', 'pause_correction_s', 'cumulative_pause_s'], errors='ignore')

    # 7.B Colonne de temps formaté (MM:SS)
    if 'elapsed_time_s' in df.columns:
        df['elapsed_time_min_sec'] = df['moving_elapsed_time_s'].apply(format_seconds_to_min_sec)

    # 8. Suppression des colonnes indésirables
    df = df.drop(columns=columns_to_drop, errors='ignore')
    
    # 9. Réorganisation des colonnes principales
    col_order_priority = [
        'timestamp', 'elapsed_time_s', 'moving_elapsed_time_s', 'elapsed_time_min_sec',
        'lap_number', 'lap_nature', 'elapsed_time_in_lap_s', 'distance', 'speed_kmh', 
        'heart_rate', 'cadence_step_per_min', 'stance_time', 'stance_time_balance', 
        'stance_time_percent', 'step_length', 'vertical_oscillation', 'vertical_ratio', 
        'altitude', 'temperature'
    ]

    remaining_cols = [col for col in df.columns if col not in col_order_priority]
    new_column_order = [col for col in col_order_priority if col in df.columns] + sorted(remaining_cols)
    
    df = df.reindex(columns=new_column_order)
    
    return df

def add_lap_info(fitfile, df):
    """
    Ajoute le numéro de lap et la nature du lap (classée par vitesse) 
    à chaque timestamp du dataframe de records.
    """
    
    if df.empty or 'timestamp' not in df.columns:
        print("DataFrame ou colonne 'timestamp' manquante pour l'ajout des laps.")
        df['lap_number'] = 1 
        df['lap_nature'] = 'Unknown'
        return df
    
    # 1. Extraction et assignation du lap_number
    laps = []
    for lap in fitfile.get_messages('lap'):
        lap_data = {}
        for field in lap:
            lap_data[field.name] = field.value
        laps.append(lap_data)
    
    if not laps:
        print("Aucun lap trouvé. Tous les enregistrements sont assignés au lap 1.")
        df['lap_number'] = 1
        df['lap_nature'] = 'Unknown'
        return df

    laps_sorted = sorted([lap for lap in laps if 'start_time' in lap and lap['start_time']], 
                         key=lambda x: x['start_time'])
    
    if not laps_sorted:
        print("Laps trouvés mais sans 'start_time'. Tous les enregistrements sont assignés au lap 1.")
        df['lap_number'] = 1
        df['lap_nature'] = 'Unknown'
        return df

    df['lap_number'] = 0
    
    # Assigner lap_number au DF de records ET ajouter le lap_number au dictionnaire lap pour la classification
    for lap_num, lap in enumerate(laps_sorted, 1):
        lap['lap_number'] = lap_num  # Assigner le numéro au lap pour la création du DF de résumé
        lap_start = pd.to_datetime(lap['start_time'])
        
        if lap_num < len(laps_sorted):
            next_lap_start = pd.to_datetime(laps_sorted[lap_num]['start_time'])
        else:
            next_lap_start = df['timestamp'].max() + timedelta(seconds=1)
        
        mask = (df['timestamp'] >= lap_start) & (df['timestamp'] < next_lap_start)
        df.loc[mask, 'lap_number'] = lap_num
        
    df.loc[df['lap_number'] == 0, 'lap_number'] = len(laps_sorted)
    # print(f"{len(laps_sorted)} laps détectés et assignés aux enregistrements") # Commenté pour éviter la sortie console
    
    # 2. Classification de la nature du lap basée sur la vitesse (avg_speed_kmh)
    
    # Création du DataFrame de résumé des laps à partir des messages 'lap'
    df_lap_summary = pd.DataFrame(laps_sorted)

    if 'avg_speed' in df_lap_summary.columns and 'lap_number' in df_lap_summary.columns:
        
        # 2.A. Conversion de avg_speed (m/s) en avg_speed_kmh (utilisant la donnée lap, pas l'agrégation des records)
        df_lap_summary['avg_speed_kmh'] = pd.to_numeric(df_lap_summary['avg_speed'], errors='coerce') 
        df_lap_summary['avg_speed_kmh'] = np.round(df_lap_summary['avg_speed_kmh'] * MS_TO_KMH, 2)
        
        # 2.B. Classer les laps
        df_lap_summary = classify_lap_nature_by_speed(df_lap_summary)
        
        # 2.C. Fusionner la nature du lap (lap_nature) dans le DF des records (df)
        df_nature = df_lap_summary[['lap_number', 'lap_nature']].copy()
        
        df = df.drop(columns=['lap_nature'], errors='ignore') 
        df = df.merge(df_nature, on='lap_number', how='left')
        
        df['lap_nature'] = df['lap_nature'].fillna('Unknown')
    else:
        # print("Avertissement: 'avg_speed' non trouvé dans les messages 'lap'. Classification de 'lap_nature' impossible.") # Commenté
        df['lap_nature'] = 'Unknown'
        
    return df

def export_lap_csv(fitfile, output_path):
    """
    Extrait toutes les données des messages 'lap', ajoute les colonnes de lisibilité
    et les exporte dans le fichier activity_data_by_lap.csv.
    """
    laps = []
    
    columns_to_drop = [
        "avg_cadence_position", "avg_combined_pedal_smoothness", "avg_fractional_cadence", "avg_left_pco", "avg_left_pedal_smoothness", "enhanced_avg_speed", "enhanced_max_speed", "total_ascent", "avg_left_power_phase", "avg_left_power_phase_peak", "avg_left_torque_effectiveness", "avg_power", "avg_power_position", "avg_right_pco", "avg_right_pedal_smoothness", "avg_right_power_phase", "avg_right_power_phase_peak", "avg_right_torque_effectiveness", "avg_stroke_distance", "end_position_lat", "end_position_long", "event_group", "event", "event_type", "first_length_index", "intensity", "lap_trigger", "left_right_balance", "max_cadence_position", "max_fractional_cadence", "max_power", "max_power_position", "max_running_cadence", "max_temperature", "message_index", "normalized_power", "num_active_lengths", "num_lengths", "sport", "stand_count", "start_position_lat", "start_position_long", "sub_sport", "swim_stroke", "time_standing", "total_calories", "total_descent", "total_fat_calories", "total_fractional_cycles", "total_work", "wkt_step_index", "unknown_124", "unknown_125", "unknown_126", "unknown_27", "unknown_28", "unknown_29", "unknown_30", "unknown_70", "unknown_72", "unknown_73", "unknown_90", "unknown_96", "unknown_97", "avg_speed", "max_speed", "start_time", "lap_duration_min_sec", "timestamp", "total_elapsed_time_min_sec"
        ]

    # Parcourir les messages 'lap'
    for lap_num, lap in enumerate(fitfile.get_messages('lap'), 1):
        lap_data = {"lap_number": lap_num}
        for field in lap:
            lap_data[field.name] = field.value
        laps.append(lap_data)

    if not laps:
        # print("Avertissement: Aucun lap trouvé pour l'exportation par lap.") # Commenté
        return None

    df_laps = pd.DataFrame(laps)
    
    if 'total_timer_time' in df_laps.columns:
        df_laps = df_laps.rename(columns={"total_timer_time": "lap_duration"})

    # Conversion des vitesses en km/h
    for speed_col in ['max_speed', 'avg_speed']:
        if speed_col in df_laps.columns:
            df_laps[speed_col] = pd.to_numeric(df_laps[speed_col], errors='coerce') 
            df_laps[f'{speed_col}_kmh'] = np.round(df_laps[speed_col] * MS_TO_KMH, 2)

    # Classification par vitesse sur le DF de laps
    if 'avg_speed_kmh' in df_laps.columns:
        # Assurer le tri pour la logique séquentielle
        df_laps = df_laps.sort_values('lap_number').reset_index(drop=True) 
        df_laps = classify_lap_nature_by_speed(df_laps) # Utilise la nouvelle fonction
        
    # Conversion du cycle de la cadence en ppm
    if 'avg_running_cadence' in df_laps.columns:
        df_laps['avg_running_cadence_step_per_min'] = df_laps['avg_running_cadence'] * 2
        df_laps = df_laps.drop(columns=['avg_running_cadence'], errors='ignore')
    
    # Suppression des colonnes indésirables
    df_laps = df_laps.drop(columns=columns_to_drop, errors='ignore')

    # Ajout des colonnes de temps formaté (MM:SS)
    for time_col in ['lap_duration', 'total_elapsed_time']:
        if time_col in df_laps.columns:
            df_laps[f'{time_col}_min_sec'] = df_laps[time_col].apply(format_seconds_to_min_sec)

    # Réorganisation des colonnes principales
    col_order_priority = [
            'lap_number',
            'lap_nature',
            'lap_duration',
            'avg_speed_kmh',
            'max_speed_kmh',
            'avg_heart_rate',
            'max_heart_rate',
            'avg_running_cadence_step_per_min',
            'avg_stance_time', 
            'avg_stance_time_balance', 
            'avg_stance_time_percent', 
            'avg_step_length', 
            'avg_vertical_oscillation', 
            'avg_vertical_ratio', 
            'total_distance', 
            'total_strides',
            'total_elapsed_time', 
    ]

    existing_priority_cols = [col for col in col_order_priority if col in df_laps.columns]
    remaining_cols = [col for col in df_laps.columns if col not in existing_priority_cols]
    new_column_order = existing_priority_cols + sorted(remaining_cols)
    
    df_laps = df_laps.reindex(columns=new_column_order)

    # Export CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_laps.to_csv(output_path, index=False)
    return df_laps

def main():
    # Deux arguments sont maintenant attendus : le chemin du fichier FIT et le chemin du dossier de sortie
    if len(sys.argv) < 3:
        # Renvoie un message JSON pour que Node.js puisse le lire
        error_msg = {"status": "error", "message": "Usage: python extract_fit.py path/to/file.fit path/to/output_dir/"}
        print(json.dumps(error_msg))
        sys.exit(1)
    
    fit_file_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    # Création de noms de fichiers uniques (basés sur le nom du fichier FIT, sans l'extension)
    file_stem = fit_file_path.stem 
    output_path_records_csv = output_dir / f"{file_stem}_records.csv"
    output_path_laps_csv = output_dir / f"{file_stem}_laps.csv"

    try:
        ff = FitFile(str(fit_file_path))
        
        # 1. Traitement et export du fichier de RECORDS 
        df = parse_fit(ff)

        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export CSV des records
        df.to_csv(output_path_records_csv, index=False)
        
        # 2. Traitement et export du fichier de LAPS
        export_lap_csv(ff, output_path_laps_csv)

        # 3. Renvoyer les chemins des fichiers en JSON pour Node.js
        result = {
            "status": "success",
            "message": "Fichiers CSV générés avec succès.",
            "records_csv_path": str(output_path_records_csv),
            "laps_csv_path": str(output_path_laps_csv)
        }
        print(json.dumps(result))

    except FileNotFoundError:
        error_msg = {"status": "error", "message": f"Erreur: Fichier FIT non trouvé à l'emplacement '{fit_file_path}'"}
        print(json.dumps(error_msg))
        sys.exit(1)
    except RuntimeError as e:
        error_msg = {"status": "error", "message": f"Erreur de traitement du fichier .fit: {e}"}
        print(json.dumps(error_msg))
        sys.exit(1)
    except Exception as e:
        error_msg = {"status": "error", "message": f"Une erreur inattendue s'est produite: {e}"}
        print(json.dumps(error_msg))
        sys.exit(1)

if __name__ == "__main__":
    main()