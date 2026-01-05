import sys
import json
from pathlib import Path
import pandas as pd
from fitparse import FitFile
import numpy as np
from datetime import datetime, timedelta

# --- Constantes ---
MS_TO_KMH = 3.6 
CADENCE_TO_SPM = 2 # 1 cycle (rpm) = 2 pas (spm)

# Seuil pour la détection des arrêts longs et immobiles pour le calcul du Moving Time
PAUSE_TIME_THRESHOLD_S = 10.0
PAUSE_DISTANCE_THRESHOLD_M = 1.0

# --- Fonctions utilitaires ---

def format_seconds_to_hms(seconds):
    """Convertit un nombre de secondes en format H:MM:SS ou MM:SS si < 1h."""
    if pd.isna(seconds):
        return None
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

# --- Fonctions principales d'extraction et de traitement ---

def parse_fit_records(fitfile):
    """
    Extrait et traite les messages 'record' du fichier FIT.
    Calcule l'elapsed time, le moving time, et convertit les unités.
    """
    rows = []
    # Champs d'intérêt prioritaires
    record_fields_of_interest = [
        "timestamp", "heart_rate", "enhanced_speed", "distance", 
        "cadence", "power", "enhanced_altitude"
    ]
    
    for rec in fitfile.get_messages('record'):
        r = {}
        for field in rec:
            if field.name in record_fields_of_interest:
                r[field.name] = field.value
        rows.append(r) 
        
    if not rows:
        raise RuntimeError("Aucun record trouvé dans le fichier .fit")
    
    df = pd.DataFrame(rows)
    
    # 1. Nettoyage et normalisation des données
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        # Calcul du temps écoulé total
        df['elapsed_time_s'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds()
        df['elapsed_time_s'] = np.round(df['elapsed_time_s'], 1)

    # 2. Conversion de la vitesse m/s -> km/h
    if 'enhanced_speed' in df.columns:
        df = df.rename(columns={'enhanced_speed': 'speed_ms'})
        df['speed_kmh'] = np.round(df['speed_ms'] * MS_TO_KMH, 2)
        df = df.drop(columns=['speed_ms'], errors='ignore')

    # 3. Conversion de la cadence cycle/min -> pas/min (spm)
    if 'cadence' in df.columns:
        df = df.rename(columns={'cadence': 'cadence_rpm'})
        # La cadence dans les fichiers FIT peut être en rpm (révolution par minute) pour le cyclisme
        # ou en pas/minute pour la course à pied. Pour la course, 1 cycle = 2 pas.
        # On assume l'approche générique pour la course :
        df['cadence_step_per_min'] = df['cadence_rpm'] * CADENCE_TO_SPM
        df['cadence_step_per_min'] = df['cadence_step_per_min'].astype('Int64', errors='ignore')
        df = df.drop(columns=['cadence_rpm'], errors='ignore')
        
    # 4. Traitement du Moving Time (Temps en mouvement)
    if 'elapsed_time_s' in df.columns and 'distance' in df.columns:
        # Calcul de la différence de temps (dt) et de distance (dd) entre les points
        df['dt'] = df['elapsed_time_s'].diff()
        df['dd'] = df['distance'].diff().fillna(0)
        
        # Détection des pauses: grand dt ET petit dd
        is_real_pause = (df['dt'] >= PAUSE_TIME_THRESHOLD_S) & (df['dd'] <= PAUSE_DISTANCE_THRESHOLD_M)
        
        # La correction est le temps de pause (dt - 1 seconde pour compter l'arrêt)
        df['pause_correction_s'] = np.where(is_real_pause, df['dt'] - 1.0, 0.0)
        df.loc[0, 'pause_correction_s'] = 0.0 # Pas de correction pour le premier point
        
        df['cumulative_pause_s'] = df['pause_correction_s'].cumsum()
        
        # Temps en mouvement = Temps total - Temps de pause cumulé
        df['moving_elapsed_time_s'] = df['elapsed_time_s'] - df['cumulative_pause_s']
        df['moving_elapsed_time_s'] = np.round(df['moving_elapsed_time_s'], 1)
        
        df = df.drop(columns=['dt', 'dd', 'pause_correction_s', 'cumulative_pause_s'], errors='ignore')

    # 5. Colonne de temps formaté (H:MM:SS ou MM:SS)
    if 'moving_elapsed_time_s' in df.columns:
        df['elapsed_time_hms'] = df['moving_elapsed_time_s'].apply(format_seconds_to_hms)
    
    # 6. Renommage et réorganisation
    if 'enhanced_altitude' in df.columns:
        df = df.rename(columns={'enhanced_altitude': 'altitude'})

    # Colonnes finales dans l'ordre de priorité
    col_order_priority = [
        'timestamp', 'elapsed_time_s', 'moving_elapsed_time_s', 'elapsed_time_hms',
        'distance', 'speed_kmh', 'heart_rate', 'cadence_step_per_min', 
        'power', 'altitude'
    ]
    
    # Garder uniquement les colonnes demandées et réorganiser
    existing_cols = [col for col in col_order_priority if col in df.columns]
    df = df[existing_cols]
    
    return df

def extract_activity_summary(fitfile):
    """
    Extrait les messages 'session' pour obtenir un résumé de l'activité.
    Détermine le sport (Trail/Road) à partir des champs 'sport' et 'sub_sport'.
    """
    session_messages = list(fitfile.get_messages('session'))
    
    if not session_messages:
        raise RuntimeError("Aucun message 'session' trouvé dans le fichier .fit")

    # Prendre la dernière (ou l'unique) session
    session_data = session_messages[-1]
    
    summary = {}
    for field in session_data:
        # Seuls les champs de haut niveau sont intéressants ici
        if field.name in ['sport', 'sub_sport', 'total_distance', 'total_elapsed_time', 'total_timer_time', 'max_heart_rate', 'avg_heart_rate', 'total_ascent', 'total_descent', 'timestamp']:
            summary[field.name] = field.value

    # Déterminer le type d'activité (Road/Trail)
    sport = summary.get('sport', 'unknown')
    sub_sport = summary.get('sub_sport', 'unknown')
    
    # Logique d'identification du Trail/Route
    if sport == 'running':
        if sub_sport == 'trail':
            activity_type = 'Trail Running'
        else:
            activity_type = 'Road Running'
    elif sport == 'cycling':
        activity_type = 'Cycling'
    else:
        activity_type = str(sport).capitalize()
    
    summary['activity_type'] = activity_type
    
    # Ajouter des métriques formatées
    total_elapsed_time = summary.get('total_elapsed_time')
    total_timer_time = summary.get('total_timer_time')
    
    if total_elapsed_time is not None:
        summary['total_elapsed_time_hms'] = format_seconds_to_hms(total_elapsed_time)
        
    if total_timer_time is not None:
        summary['total_timer_time_hms'] = format_seconds_to_hms(total_timer_time)
        
    # Nettoyage des clés brutes qui ne seront pas utilisées pour l'affichage final
    keys_to_drop = ['sport', 'sub_sport']
    for key in keys_to_drop:
        summary.pop(key, None)

    return summary

def main():
    """Fonction principale pour l'exécution du script."""
    if len(sys.argv) < 3:
        error_msg = {"status": "error", "message": "Usage: python extract_fit.py path/to/file.fit path/to/output_dir/"}
        print(json.dumps(error_msg))
        sys.exit(1)
    
    fit_file_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    file_stem = fit_file_path.stem 
    output_path_records_csv = output_dir / f"{file_stem}_records.csv"
    output_path_summary_json = output_dir / f"{file_stem}_activity_summary.json"

    try:
        ff = FitFile(str(fit_file_path))
        
        # Création du dossier de sortie si nécessaire
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Traitement et export des RECORDS (Point par point)
        df_records = parse_fit_records(ff)
        df_records.to_csv(output_path_records_csv, index=False)
        
        # 2. Traitement et export du RÉSUMÉ de l'activité (Haut niveau)
        activity_summary = extract_activity_summary(ff)
        with open(output_path_summary_json, 'w') as f:
            json.dump(activity_summary, f, indent=4)

        # 3. Renvoyer les chemins des fichiers en JSON
        result = {
            "status": "success",
            "message": "Fichiers CSV et JSON générés avec succès.",
            "records_csv_path": str(output_path_records_csv),
            "summary_json_path": str(output_path_summary_json)
        }
        print(json.dumps(result))

    except Exception as e:
        error_msg = {"status": "error", "message": f"Une erreur s'est produite lors du traitement du fichier .fit: {e}"}
        print(json.dumps(error_msg))
        sys.exit(1)

if __name__ == "__main__":
    main()