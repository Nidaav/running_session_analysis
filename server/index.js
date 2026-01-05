// server/index.js

const express = require('express');
const multer = require('multer');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process'); 

const app = express();
const port = 5000; 

// Configuration CORS pour autoriser les requêtes depuis votre application React (port 3000 par défaut)
app.use(cors({
  origin: 'http://localhost:3000' 
}));

// --- Chemins du Backend ---
const uploadDir = path.join(__dirname, 'uploads');
const resultsDir = path.join(__dirname, 'results');
const PYTHON_SCRIPT_PATH = path.join(__dirname, 'extract_fit_file.py'); 

// --- Configuration du stockage pour Multer ---
const storage = multer.diskStorage({
  // Stocker dans le dossier 'uploads'
  destination: (req, file, cb) => {
    cb(null, uploadDir); 
  },
  // Renommer le fichier pour qu'il soit unique et préserve l'extension
  filename: (req, file, cb) => {
    const ext = path.extname(file.originalname);
    cb(null, Date.now() + '-' + file.fieldname + ext);
  }
});

const upload = multer({ storage: storage });

// --- Route d'Upload ---
app.post('/upload', upload.single('fitFile'), (req, res) => {
  if (!req.file) {
    return res.status(400).send('Aucun fichier n\'a été envoyé.');
  }
  
  const fitFilePath = req.file.path; // Chemin du fichier FIT stocké par Multer

  console.log(`Fichier reçu et stocké : ${fitFilePath}`);
  
  // --- Exécution du Script Python ---

  const pythonExecutable = 'python'; 
  
  // Arguments: 1. Chemin du script, 2. Chemin du fichier FIT, 3. Chemin du dossier de sortie
  const pythonProcess = spawn(pythonExecutable, [PYTHON_SCRIPT_PATH, fitFilePath, resultsDir]);
  
  let pythonOutput = '';
  let pythonError = '';

  // AJOUT DE L'ÉCOUTEUR 'ERROR' pour capturer les erreurs de lancement
  pythonProcess.on('error', (err) => {
      console.error('Erreur fatale lors du lancement du processus Python (exécutable introuvable ?):', err.message);
      // Envoyer une réponse au client pour débloquer la requête
      if (!res.headersSent) {
          res.status(500).json({
              message: `Erreur de lancement du script Python: ${err.message}`,
              error: 'PYTHON_EXEC_NOT_FOUND'
          });
      }
  });

  // 1. Récupérer la sortie (stdout) - Le JSON résultat y est envoyé
  pythonProcess.stdout.on('data', (data) => {
    pythonOutput += data.toString();
  });

  // 2. Récupérer les erreurs (stderr)
  pythonProcess.stderr.on('data', (data) => {
    pythonError += data.toString();
    console.error(`Python STDERR: ${data.toString().trim()}`);
  });

  // 3. Gérer la fin du processus
  pythonProcess.on('close', (code) => {
    // Supprimer le fichier .fit téléchargé pour le nettoyage
    fs.unlink(fitFilePath, (err) => {
         if (err) console.error("Erreur lors de la suppression du fichier FIT temporaire:", err);
         else console.log(`Fichier FIT temporaire supprimé: ${fitFilePath}`);
    });

    if (code === 0) {
      try {
        // Le script Python envoie le résultat en JSON à STDOUT
        const result = JSON.parse(pythonOutput.trim());
        
        if (result.status === 'success') {
             // Succès: Renvoyer le chemin des CSV
             console.log(`Analyse Python terminée avec succès.`);
             res.json({ 
                 message: 'Fichier analysé, CSV stockés dans le backend.',
                 recordsCsvPath: result.records_csv_path,
                 lapsCsvPath: result.laps_csv_path
             });
        } else {
             // Échec : Le script Python a renvoyé un statut d'erreur (géré dans le try/catch Python)
             console.error(`Erreur d'analyse Python: ${result.message}`);
             res.status(500).json({
                 message: 'Erreur lors du traitement du fichier par les scripts d\'analyse.',
                 errorDetails: result.message
             });
        }
      } catch (e) {
          // Erreur de parsing JSON (si le script Python n'a pas renvoyé de JSON valide)
          console.error(`Erreur de parsing JSON ou de sortie Python inattendue: ${e}`);
          console.log(`Sortie brute Python: ${pythonOutput}`);
          res.status(500).json({
              message: 'Erreur interne du serveur lors de l\'analyse des données.',
              error: pythonError || 'Sortie Python non conforme.'
          });
      }
    } else {
      // Échec: Le processus Python a échoué (code != 0)
      console.error(`Processus Python échoué (Code ${code}).`);
      res.status(500).json({
        message: 'Erreur du processus Python. Vérifiez l\'exécutable Python ou les dépendances.',
        error: pythonError,
        output: pythonOutput
      });
    }
  });
});

app.listen(port, () => {
  console.log(`Serveur Backend démarré sur http://localhost:${port}`);
});