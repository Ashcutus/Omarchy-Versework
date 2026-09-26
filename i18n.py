"""Interface translations. Creative content and model data are never translated here."""
import os

LANGUAGES = [('system', 'System language'), ('en', 'English'), ('de', 'Deutsch'), ('es', 'Español'), ('fr', 'Français')]
# English | German | Spanish | French. Keep format placeholders identical.
_ROWS = '''
Drum feel|Schlagzeuggefühl|Carácter de la batería|Jeu de batterie
Machine-perfect|Maschinenpräzise|Precisión de máquina|Précision mécanique
Sunday night in the pub|Sonntagabend in der Kneipe|Domingo por la noche en el pub|Dimanche soir au pub
Tight session drummer|Präziser Studioschlagzeuger|Baterista de estudio preciso|Batteur de studio précis
Relaxed pocket|Entspannter Groove|Ritmo relajado|Groove détendu
Loose live drummer|Lockerer Liveschlagzeuger|Baterista en directo suelto|Batteur live décontracté
Sloppy Sunday night in the pub|Schlampiger Sonntagabend in der Kneipe|Domingo desaliñado en el pub|Dimanche soir brouillon au pub
Your lyrics (optional)|Deine Songtexte (optional)|Tus letras (opcional)|Vos paroles (facultatives)
Leave empty to have Ollama write the lyrics.|Leer lassen, damit Ollama den Text schreibt.|Déjalo vacío para que Ollama escriba la letra.|Laissez vide pour qu’Ollama écrive les paroles.
Offer improvement suggestions|Verbesserungsvorschläge anbieten|Ofrecer sugerencias de mejora|Proposer des améliorations
Leave my lyrics unchanged|Meine Songtexte unverändert lassen|Dejar mi letra sin cambios|Laisser mes paroles inchangées
Rewrite limits|Überarbeitungslimits|Límites de revisión|Limites de réécriture
Disable rewrite limits completely|Überarbeitungslimits vollständig deaktivieren|Desactivar completamente los límites de revisión|Désactiver complètement les limites de réécriture
Default rewrites per song|Standardüberarbeitungen pro Song|Revisiones predeterminadas por canción|Réécritures par chanson par défaut
Refresh lyrics|Songtext auffrischen|Renovar letra|Retravailler les paroles
Light polish|Leicht überarbeiten|Retoque ligero|Retouche légère
Stronger chorus|Stärkerer Refrain|Estribillo más fuerte|Refrain plus marquant
Fresh lyrics|Neuer Songtext|Letra nueva|Nouvelles paroles
Update delivery cues|Vortragshinweise aktualisieren|Actualizar indicaciones de interpretación|Actualiser les indications d’interprétation
Choose a starting point, then review the instructions before rewriting.|Wähle einen Ansatz und prüfe die Anweisungen vor der Überarbeitung.|Elige un punto de partida y revisa las instrucciones antes de reescribir.|Choisissez un point de départ puis vérifiez les instructions avant la réécriture.
Uses the normal rewrite allowance when you start rewriting. Locked fields remain unchanged.|Verbraucht beim Start eine reguläre Überarbeitung. Gesperrte Felder bleiben unverändert.|Usa una revisión normal al empezar. Los campos bloqueados no cambian.|Utilise une révision normale au lancement. Les champs verrouillés restent inchangés.
Performance feel|Spielgefühl|Carácter de la interpretación|Caractère de l’interprétation
Natural and understated|Natürlich und zurückhaltend|Natural y contenida|Naturelle et sobre
Live-room performance|Live im Raum|Interpretación en directo|Interprétation en salle
Tight and polished|Präzise und ausgefeilt|Precisa y pulida|Précise et soignée
App updates|App-Updates|Actualizaciones de la aplicación|Mises à jour de l’application
Check GitHub for the latest version of Versework.|Suche auf GitHub nach der neuesten Version von Versework.|Busca la última versión de Versework en GitHub.|Recherchez la dernière version de Versework sur GitHub.
Check for updates|Nach Updates suchen|Buscar actualizaciones|Rechercher des mises à jour
Install update|Update installieren|Instalar actualización|Installer la mise à jour
Restart Versework|Versework neu starten|Reiniciar Versework|Redémarrer Versework
Update installed. Restart Versework to use it.|Update installiert. Starte Versework neu.|Actualización instalada. Reinicia Versework para usarla.|Mise à jour installée. Redémarrez Versework pour l’utiliser.
An update check or installation is already running.|Eine Updateprüfung oder Installation läuft bereits.|Ya hay una búsqueda o instalación en curso.|Une recherche ou une installation est déjà en cours.
Update failed: {error}|Update fehlgeschlagen: {error}|Error de actualización: {error}|Échec de la mise à jour : {error}
Versework is up to date.|Versework ist auf dem neuesten Stand.|Versework está actualizado.|Versework est à jour.
An update is available. Your songs and settings will be preserved.|Ein Update ist verfügbar. Songs und Einstellungen bleiben erhalten.|Hay una actualización disponible. Se conservarán tus canciones y ajustes.|Une mise à jour est disponible. Vos chansons et réglages seront conservés.
Open the installed app to update. Run install.sh once if needed.|Öffne die installierte App zum Aktualisieren. Führe bei Bedarf einmal install.sh aus.|Abre la aplicación instalada para actualizar. Ejecuta install.sh una vez si es necesario.|Ouvrez l’application installée pour la mettre à jour. Exécutez install.sh une fois si nécessaire.
Checking for updates…|Suche nach Updates…|Buscando actualizaciones…|Recherche de mises à jour…
Installing update…|Update wird installiert…|Instalando actualización…|Installation de la mise à jour…
Wait for the update to finish before closing.|Warte vor dem Schließen, bis das Update abgeschlossen ist.|Espera a que termine la actualización antes de cerrar.|Attendez la fin de la mise à jour avant de fermer.
Production|Produktion|Producción|Production
Production direction|Produktionsvorgaben|Dirección de producción|Direction de production
Dynamics|Dynamik|Dinámica|Dynamique
Vocal delivery|Gesangsstil|Interpretación vocal|Interprétation vocale
Follow style|Stil folgen|Seguir el estilo|Suivre le style
Stripped back|Minimalistisch|Minimalista|Épurée
Restrained|Zurückhaltend|Contenida|Sobre
Balanced|Ausgewogen|Equilibrada|Équilibrée
Full production|Volle Produktion|Producción completa|Production ample
Steady and contained|Gleichmäßig und verhalten|Constante y contenida|Stable et contenue
Gentle build|Sanfte Steigerung|Crecimiento suave|Progression douce
Dramatic build|Dramatische Steigerung|Crecimiento dramático|Progression dramatique
Intimate solo|Intimer Sologesang|Solo íntimo|Solo intime
Natural lead|Natürliche Hauptstimme|Voz principal natural|Voix principale naturelle
Layered vocals|Mehrschichtiger Gesang|Voces en capas|Voix superposées
Arrangement and delivery notes|Hinweise zu Arrangement und Vortrag|Notas de arreglo e interpretación|Notes d’arrangement et d’interprétation
Applies to the next draft or rewrite. Suno may interpret these directions differently.|Gilt für den nächsten Entwurf oder die nächste Überarbeitung. Suno kann diese Vorgaben anders interpretieren.|Se aplica al próximo borrador o revisión. Suno puede interpretar estas indicaciones de otra manera.|S’applique au prochain brouillon ou à la prochaine révision. Suno peut interpréter ces indications différemment.
Production direction saved for the next draft or rewrite.|Produktionsvorgaben für den nächsten Entwurf oder die nächste Überarbeitung gespeichert.|Dirección de producción guardada para el próximo borrador o revisión.|Direction de production enregistrée pour le prochain brouillon ou la prochaine révision.
Open Suno|Suno öffnen|Abrir Suno|Ouvrir Suno
Open Suno in your browser to log in or create music.|Öffne Suno im Browser, um dich anzumelden oder Musik zu erstellen.|Abre Suno en tu navegador para iniciar sesión o crear música.|Ouvrez Suno dans votre navigateur pour vous connecter ou créer de la musique.
Could not open Suno: {error}|Suno konnte nicht geöffnet werden: {error}|No se pudo abrir Suno: {error}|Impossible d’ouvrir Suno : {error}
Review songs|Songs überprüfen|Revisar canciones|Réviser les chansons
Select songs and enter feedback.|Wähle Songs und gib Feedback ein.|Selecciona canciones e introduce comentarios.|Sélectionnez des chansons et ajoutez des commentaires.
Rewrite selected songs|Ausgewählte Songs überarbeiten|Reescribir canciones seleccionadas|Réécrire les chansons sélectionnées
Songs|Songs|Canciones|Chansons
Collections|Sammlungen|Colecciones|Collections
New song|Neuer Song|Nueva canción|Nouvelle chanson
New collection|Neue Sammlung|Nueva colección|Nouvelle collection
Settings|Einstellungen|Ajustes|Paramètres
Close|Schließen|Cerrar|Fermer
Apply|Anwenden|Aplicar|Appliquer
Cancel|Abbrechen|Cancelar|Annuler
Save|Speichern|Guardar|Enregistrer
Copy|Kopieren|Copiar|Copier
Copy song|Song kopieren|Copiar canción|Copier la chanson
Copy all|Alles kopieren|Copiar todo|Tout copier
Copied|Kopiert|Copiado|Copié
Write song|Song schreiben|Escribir canción|Écrire la chanson
Write these songs|Diese Songs schreiben|Escribir estas canciones|Écrire ces chansons
Write remaining drafts|Fehlende Entwürfe schreiben|Escribir borradores pendientes|Écrire les brouillons restants
Stop writing|Schreiben stoppen|Detener escritura|Arrêter l’écriture
Saved on this computer|Auf diesem Computer gespeichert|Guardado en este equipo|Enregistré sur cet ordinateur
Your songs, your way.|Deine Songs, auf deine Art.|Tus canciones, a tu manera.|Vos chansons, à votre façon.
Start with a song. Organise it later.|Beginne mit einem Song. Organisiere ihn später.|Empieza con una canción. Organízala después.|Commencez par une chanson. Organisez-la ensuite.
Write independently, or gather songs around a theme and shape an album or EP.|Schreibe einzelne Songs oder sammle sie zu einem Thema für ein Album oder eine EP.|Escribe canciones independientes o reúnelas en torno a un tema para un álbum o EP.|Écrivez des chansons indépendantes ou réunissez-les autour d’un thème pour un album ou un EP.
Search songs|Songs suchen|Buscar canciones|Rechercher des chansons
No songs yet|Noch keine Songs|Aún no hay canciones|Aucune chanson pour le moment
No matching songs|Keine passenden Songs|No hay canciones coincidentes|Aucune chanson correspondante
Collection|Sammlung|Colección|Collection
Album|Album|Álbum|Album
EP|EP|EP|EP
Theme|Thema|Tema|Thème
Optional theme|Optionales Thema|Tema opcional|Thème facultatif
Manage collection|Sammlung verwalten|Gestionar colección|Gérer la collection
Songs: {n}|Songs: {n}|Canciones: {n}|Chansons : {n}
Export|Exportieren|Exportar|Exporter
Export songs|Songs exportieren|Exportar canciones|Exporter les chansons
Export song|Song exportieren|Exportar canción|Exporter la chanson
Export here|Hier exportieren|Exportar aquí|Exporter ici
Choose export folder|Exportordner wählen|Elegir carpeta de exportación|Choisir le dossier d’exportation
Save text and history|Text und Verlauf speichern|Guardar texto e historial|Enregistrer le texte et l’historique
Copied to clipboard.|In die Zwischenablage kopiert.|Copiado al portapapeles.|Copié dans le presse-papiers.
Exported to {path}|Exportiert nach {path}|Exportado a {path}|Exporté vers {path}
Song title|Songtitel|Título de la canción|Titre de la chanson
Working title|Arbeitstitel|Título provisional|Titre provisoire
Lyrics|Songtext|Letra|Paroles
Sound|Klang|Sonido|Son
Review|Überprüfen|Revisión|Révision
Style prompt|Stilbeschreibung|Descripción del estilo|Description du style
Exclusions|Ausschlüsse|Exclusiones|Exclusions
Vocal gender|Gesangsstimme|Voz|Voix
Weirdness %|Experimentierfreude %|Rareza %|Excentricité %
Style influence %|Stileinfluss %|Influencia del estilo %|Influence du style %
Variety level|Variationsgrad|Nivel de variedad|Niveau de variété
Lock|Sperren|Bloquear|Verrouiller
Lock fields to preserve them exactly during rewrites.|Sperre Felder, um sie bei Überarbeitungen exakt zu erhalten.|Bloquea campos para conservarlos exactamente al reescribir.|Verrouillez les champs à conserver exactement lors des réécritures.
Approve song|Song freigeben|Aprobar canción|Approuver la chanson
Reopen|Erneut öffnen|Reabrir|Rouvrir
Versions|Versionen|Versiones|Versions
Approved|Freigegeben|Aprobada|Approuvée
Not drafted|Noch kein Entwurf|Sin borrador|Pas encore de brouillon
Ready for review|Bereit zur Überprüfung|Lista para revisar|Prête à être révisée
Limit reached · review needed|Limit erreicht · Überprüfung nötig|Límite alcanzado · revisión necesaria|Limite atteinte · révision nécessaire
Rewrites: {used}/{limit}|Überarbeitungen: {used}/{limit}|Reescrituras: {used}/{limit}|Réécritures : {used}/{limit}
Feedback|Feedback|Comentarios|Commentaires
Describe what to change, or add listening notes from Suno.|Beschreibe Änderungen oder ergänze Hörnotizen aus Suno.|Describe los cambios o añade notas tras escuchar en Suno.|Décrivez les changements ou ajoutez vos notes d’écoute de Suno.
Rewrite song|Song überarbeiten|Reescribir canción|Réécrire la chanson
Song brief|Song-Idee|Idea de la canción|Idée de la chanson
Lyric language|Sprache des Songtexts|Idioma de la letra|Langue des paroles
Song count|Anzahl der Songs|Número de canciones|Nombre de chansons
Minimum length (seconds)|Mindestlänge (Sekunden)|Duración mínima (segundos)|Durée minimale (secondes)
Maximum length (seconds)|Höchstlänge (Sekunden)|Duración máxima (segundos)|Durée maximale (secondes)
AI rewrites per song|KI-Überarbeitungen pro Song|Reescrituras por canción|Réécritures par chanson
Collection (optional)|Sammlung (optional)|Colección (opcional)|Collection (facultative)
No collection|Keine Sammlung|Sin colección|Aucune collection
Create|Erstellen|Crear|Créer
Untitled song|Unbenannter Song|Canción sin título|Chanson sans titre
Write an original song from this brief.|Schreibe einen eigenen Song aus dieser Idee.|Escribe una canción original a partir de esta idea.|Écrivez une chanson originale à partir de cette idée.
Target: {minimum}–{maximum} seconds|Ziel: {minimum}–{maximum} Sekunden|Objetivo: {minimum}–{maximum} segundos|Objectif : {minimum}–{maximum} secondes
Duration is a writing target; Suno determines the audio length.|Die Dauer ist ein Schreibziel; Suno bestimmt die Audiolänge.|La duración orienta la escritura; Suno determina la duración del audio.|La durée guide l’écriture ; Suno détermine la durée de l’audio.
Name|Name|Nombre|Nom
Format|Format|Formato|Format
Choose songs and their running order. Their drafts and history stay intact.|Wähle Songs und Reihenfolge. Entwürfe und Verlauf bleiben erhalten.|Elige canciones y su orden. Los borradores y el historial se conservan.|Choisissez les chansons et leur ordre. Les brouillons et l’historique sont conservés.
Move up|Nach oben|Subir|Monter
Move down|Nach unten|Bajar|Descendre
Save collection|Sammlung speichern|Guardar colección|Enregistrer la collection
Organise song|Song zuordnen|Organizar canción|Organiser la chanson
Add this song to any collection. Unchecking removes only the membership.|Ordne diesen Song Sammlungen zu. Abwählen entfernt nur die Zuordnung.|Añade esta canción a cualquier colección. Desmarcar solo elimina la asociación.|Ajoutez cette chanson à des collections. Décocher retire uniquement l’association.
No collections yet. Create one from the sidebar.|Noch keine Sammlungen. Erstelle eine in der Seitenleiste.|Aún no hay colecciones. Crea una en la barra lateral.|Aucune collection. Créez-en une dans la barre latérale.
Appearance|Darstellung|Apariencia|Apparence
Colours|Farben|Colores|Couleurs
Follow Omarchy theme|Omarchy-Design folgen|Seguir tema de Omarchy|Suivre le thème d’Omarchy
Custom colours|Eigene Farben|Colores personalizados|Couleurs personnalisées
Background|Hintergrund|Fondo|Arrière-plan
Surface|Flächen|Superficie|Surfaces
Text|Text|Texto|Texte
Accent|Akzent|Acento|Accent
Restore theme colours|Designfarben wiederherstellen|Restaurar colores del tema|Restaurer les couleurs du thème
Colours affect Versework only. Theme changes are followed automatically.|Farben gelten nur für Versework. Designänderungen werden automatisch übernommen.|Los colores solo afectan a Versework. Los cambios del tema se siguen automáticamente.|Les couleurs concernent uniquement Versework. Les changements de thème sont suivis automatiquement.
Language|Sprache|Idioma|Langue
Interface language|Sprache der Oberfläche|Idioma de la interfaz|Langue de l’interface
System language|Systemsprache|Idioma del sistema|Langue du système
System language: {language}|Systemsprache: {language}|Idioma del sistema: {language}|Langue du système : {language}
Only the interface changes. Song text and lyric language stay unchanged.|Nur die Oberfläche ändert sich. Songtexte und deren Sprache bleiben unverändert.|Solo cambia la interfaz. La letra y su idioma no cambian.|Seule l’interface change. Les paroles et leur langue restent inchangées.
Local writing|Lokales Schreiben|Escritura local|Écriture locale
Versework needs Ollama running before it can write songs. After a restart, start it here and check that your local model is available.|Versework benötigt Ollama, um Songs zu schreiben. Starte es nach einem Neustart hier und prüfe, ob dein lokales Modell verfügbar ist.|Versework necesita que Ollama esté en ejecución para escribir canciones. Después de reiniciar, inícialo aquí y comprueba que tu modelo local esté disponible.|Versework doit pouvoir joindre Ollama pour écrire des chansons. Après un redémarrage, démarrez-le ici et vérifiez que votre modèle local est disponible.
Ollama connection has not been checked yet.|Die Ollama-Verbindung wurde noch nicht geprüft.|Aún no se ha comprobado la conexión con Ollama.|La connexion à Ollama n’a pas encore été vérifiée.
Ollama is running, but no local models are installed. Run setup-ollama.sh to install the default model.|Ollama läuft, aber es sind keine lokalen Modelle installiert. Führe setup-ollama.sh aus, um das Standardmodell zu installieren.|Ollama está en ejecución, pero no hay modelos locales instalados. Ejecuta setup-ollama.sh para instalar el modelo predeterminado.|Ollama fonctionne, mais aucun modèle local n’est installé. Exécutez setup-ollama.sh pour installer le modèle par défaut.
Ollama is not installed. Open a terminal in the Versework folder and run ./setup-ollama.sh.|Ollama ist nicht installiert. Öffne ein Terminal im Versework-Ordner und führe ./setup-ollama.sh aus.|Ollama no está instalado. Abre un terminal en la carpeta Versework y ejecuta ./setup-ollama.sh.|Ollama n’est pas installé. Ouvrez un terminal dans le dossier Versework et exécutez ./setup-ollama.sh.
Starting Ollama…|Ollama wird gestartet…|Iniciando Ollama…|Démarrage d’Ollama…
Ollama did not start. Check the service log at {path}.|Ollama wurde nicht gestartet. Prüfe das Dienstprotokoll unter {path}.|Ollama no se inició. Consulta el registro del servicio en {path}.|Ollama n’a pas démarré. Consultez le journal du service dans {path}.
Could not start Ollama: {error}|Ollama konnte nicht gestartet werden: {error}|No se pudo iniciar Ollama: {error}|Impossible de démarrer Ollama : {error}
Ollama is running, but no local models are installed. Run ./setup-ollama.sh from the Versework folder.|Ollama läuft, aber es sind keine lokalen Modelle installiert. Führe ./setup-ollama.sh im Versework-Ordner aus.|Ollama está en ejecución, pero no hay modelos locales instalados. Ejecuta ./setup-ollama.sh desde la carpeta Versework.|Ollama fonctionne, mais aucun modèle local n’est installé. Exécutez ./setup-ollama.sh depuis le dossier Versework.
Local model|Lokales Modell|Modelo local|Modèle local
Check connection|Verbindung prüfen|Comprobar conexión|Vérifier la connexion
Start Ollama|Ollama starten|Iniciar Ollama|Démarrer Ollama
Checking local Ollama…|Lokales Ollama wird geprüft…|Comprobando Ollama local…|Vérification d’Ollama local…
Connected: {models}|Verbunden: {models}|Conectado: {models}|Connecté : {models}
No local models installed.|Keine lokalen Modelle installiert.|No hay modelos locales instalados.|Aucun modèle local installé.
Ollama is not installed. Run setup-ollama.sh first.|Ollama ist nicht installiert. Führe zuerst setup-ollama.sh aus.|Ollama no está instalado. Ejecuta setup-ollama.sh primero.|Ollama n’est pas installé. Exécutez d’abord setup-ollama.sh.
Ollama start requested. Check connection in a moment.|Ollama-Start angefordert. Prüfe gleich die Verbindung.|Se ha solicitado iniciar Ollama. Comprueba la conexión en un momento.|Démarrage d’Ollama demandé. Vérifiez la connexion dans un instant.
Choose a local model.|Wähle ein lokales Modell.|Elige un modelo local.|Choisissez un modèle local.
Only connects to Ollama on this computer.|Verbindet sich nur mit Ollama auf diesem Computer.|Solo se conecta a Ollama en este equipo.|Se connecte uniquement à Ollama sur cet ordinateur.
Settings saved.|Einstellungen gespeichert.|Ajustes guardados.|Paramètres enregistrés.
Edits saved.|Änderungen gespeichert.|Cambios guardados.|Modifications enregistrées.
Add feedback before requesting a rewrite.|Gib vor der Überarbeitung Feedback ein.|Añade comentarios antes de solicitar una reescritura.|Ajoutez des commentaires avant de demander une réécriture.
Finish or stop writing first.|Beende oder stoppe zuerst das Schreiben.|Termina o detén la escritura primero.|Terminez ou arrêtez d’abord l’écriture.
All drafts are written.|Alle Entwürfe sind fertig.|Todos los borradores están escritos.|Tous les brouillons sont écrits.
Connecting to {model}…|Verbinde mit {model}…|Conectando con {model}…|Connexion à {model}…
Writing song {number}/{count}…|Schreibe Song {number}/{count}…|Escribiendo canción {number}/{count}…|Écriture de la chanson {number}/{count}…
Song generation failed|Songgenerierung fehlgeschlagen|Error al generar la canción|Échec de la génération de la chanson
Song generation failed for {count} item(s). You can retry after fixing the issue. Details: {details}|Die Songgenerierung ist für {count} Element(e) fehlgeschlagen. Nach Behebung des Problems kannst du es erneut versuchen. Details: {details}|Falló la generación de {count} elemento(s). Puedes volver a intentarlo tras corregir el problema. Detalles: {details}|La génération a échoué pour {count} élément(s). Vous pourrez réessayer après avoir résolu le problème. Détails : {details}
Writing song {number}/{count} · {size} characters|Schreibe Song {number}/{count} · {size} Zeichen|Escribiendo canción {number}/{count} · {size} caracteres|Écriture de la chanson {number}/{count} · {size} caractères
Drafts saved. Ready for review.|Entwürfe gespeichert. Bereit zur Überprüfung.|Borradores guardados. Listos para revisar.|Brouillons enregistrés. Prêts à être révisés.
Writing stopped. Completed drafts are saved.|Schreiben gestoppt. Fertige Entwürfe sind gespeichert.|Escritura detenida. Los borradores completos están guardados.|Écriture arrêtée. Les brouillons terminés sont enregistrés.
Stopping after Ollama responds…|Stoppe nach der Antwort von Ollama…|Deteniendo tras la respuesta de Ollama…|Arrêt après la réponse d’Ollama…
This song cannot be rewritten until reopened or its limit allows it.|Dieser Song ist gesperrt oder hat sein Limit erreicht.|Esta canción está aprobada o ha alcanzado su límite.|Cette chanson est approuvée ou a atteint sa limite.
Version history|Versionsverlauf|Historial de versiones|Historique des versions
Restoring never resets the rewrite counter.|Wiederherstellen setzt den Zähler nie zurück.|Restaurar nunca reinicia el contador de reescrituras.|La restauration ne réinitialise jamais le compteur de réécritures.
Version {number} · {kind} · {date}|Version {number} · {kind} · {date}|Versión {number} · {kind} · {date}|Version {number} · {kind} · {date}
Restore version|Version wiederherstellen|Restaurar versión|Restaurer la version
Version restored.|Version wiederhergestellt.|Versión restaurada.|Version restaurée.
initial|Erster Entwurf|Inicial|Initiale
rewrite|Überarbeitung|Reescritura|Réécriture
edit|Bearbeitung|Edición|Modification
restore|Wiederherstellung|Restauración|Restauration
male|Männlich|Masculina|Masculine
female|Weiblich|Femenina|Féminine
mixed|Gemischt|Mixta|Mixte
unspecified|Nicht festgelegt|Sin especificar|Non précisée
instrumental|Instrumental|Instrumental|Instrumentale
off|Aus|Desactivado|Désactivé
normal|Normal|Normal|Normal
high|Hoch|Alto|Élevé
extra|Extra|Extra|Extra
max|Maximum|Máximo|Maximum
Production presets|Produktionsvorlagen|Preajustes de producción|Préréglages de production
Suno model|Suno-Modell|Modelo de Suno|Modèle Suno
Default Suno model for new songs|Standard-Suno-Modell für neue Songs|Modelo de Suno predeterminado para canciones nuevas|Modèle Suno par défaut pour les nouvelles chansons
v6 — Precise|v6 — Präzise|v6 — Preciso|v6 — Précis
v6-wild — Experimental|v6-wild — Experimentell|v6-wild — Experimental|v6-wild — Expérimental
v6-mini — Fast|v6-mini — Schnell|v6-mini — Rápido|v6-mini — Rapide
Balanced, reliable and polished; choose this when you know what you want.|Ausgewogen, zuverlässig und ausgefeilt; wähle dieses Modell, wenn du genau weißt, was du möchtest.|Equilibrado, fiable y pulido; elígelo cuando sepas lo que quieres.|Équilibré, fiable et soigné ; choisissez-le si vous savez ce que vous voulez.
More varied and unpredictable; choose this to explore unexpected directions.|Vielfältiger und unvorhersehbarer; wähle dieses Modell für überraschende Richtungen.|Más variado e impredecible; elígelo para explorar caminos inesperados.|Plus varié et imprévisible ; choisissez-le pour explorer des directions inattendues.
A faster, lighter model; focus on the central idea and essential details.|Ein schnelleres, leichteres Modell; konzentriere dich auf die Grundidee und wichtige Details.|Un modelo más rápido y ligero; céntrate en la idea principal y los detalles esenciales.|Un modèle plus rapide et léger ; concentrez-vous sur l’idée centrale et les détails essentiels.
Choose the same Suno model in Create. Versework prepares the prompts but does not create the audio.|Wähle in Suno Create dasselbe Modell. Versework bereitet die Prompts vor, erstellt aber kein Audio.|Elige el mismo modelo en Suno Create. Versework prepara los prompts, pero no genera el audio.|Choisissez le même modèle dans Suno Create. Versework prépare les prompts mais ne génère pas l’audio.
Choose a preset|Vorlage wählen|Elegir un preajuste|Choisir un préréglage
Machine-perfect → Sunday night in the pub|Maschinenpräzise → Sonntagabend in der Kneipe|Precisión mecánica → Domingo por la noche en el bar|Précision mécanique → Dimanche soir au pub
Preset name|Name der Vorlage|Nombre del preajuste|Nom du préréglage
Enter a preset name.|Gib einen Namen für die Vorlage ein.|Introduce un nombre para el preajuste.|Saisissez un nom de préréglage.
Preset saved.|Vorlage gespeichert.|Preajuste guardado.|Préréglage enregistré.
Save production preset|Produktionsvorlage speichern|Guardar preajuste de producción|Enregistrer le préréglage de production
Production preview|Produktionsvorschau|Vista previa de producción|Aperçu de production
These directions are added to the next draft. Locked fields are preserved.|Diese Vorgaben werden dem nächsten Entwurf hinzugefügt. Gesperrte Felder bleiben erhalten.|Estas instrucciones se añaden al próximo borrador. Los campos bloqueados se conservan.|Ces consignes sont ajoutées au prochain brouillon. Les champs verrouillés sont conservés.
Preserved|Beibehalten|Conservado|Conservé
Review proposed changes|Vorgeschlagene Änderungen prüfen|Revisar cambios propuestos|Examiner les modifications proposées
Choose the changes to keep. Unchecked fields retain your saved version.|Wähle die gewünschten Änderungen. Nicht ausgewählte Felder behalten die gespeicherte Version.|Elige los cambios que deseas conservar. Los campos sin marcar mantienen la versión guardada.|Choisissez les modifications à conserver. Les champs décochés gardent votre version enregistrée.
Saved|Gespeichert|Guardado|Enregistré
Proposed|Vorgeschlagen|Propuesto|Proposé
Select at least one change, or discard this proposal.|Wähle mindestens eine Änderung oder verwirf diesen Vorschlag.|Selecciona al menos un cambio o descarta esta propuesta.|Sélectionnez au moins une modification ou abandonnez cette proposition.
Accept selected changes|Ausgewählte Änderungen übernehmen|Aceptar cambios seleccionados|Accepter les modifications sélectionnées
Discard proposal|Vorschlag verwerfen|Descartar propuesta|Abandonner la proposition
Song tools|Song-Werkzeuge|Herramientas de canción|Outils de chanson
Suno result link|Link zum Suno-Ergebnis|Enlace al resultado de Suno|Lien du résultat Suno
Listening notes — drums, vocals, arrangement and duration|Hörnotizen — Schlagzeug, Gesang, Arrangement und Dauer|Notas de escucha — batería, voz, arreglo y duración|Notes d'écoute — batterie, voix, arrangement et durée
Duplicate song|Song duplizieren|Duplicar canción|Dupliquer la chanson
Restore to active songs|Zu aktiven Songs zurückholen|Restaurar a canciones activas|Rétablir parmi les chansons actives
Archive song|Song archivieren|Archivar canción|Archiver la chanson
Move to trash|In den Papierkorb verschieben|Mover a la papelera|Mettre à la corbeille
Save listening notes|Hörnotizen speichern|Guardar notas de escucha|Enregistrer les notes d'écoute
Backups and recovery|Sicherung und Wiederherstellung|Copias de seguridad y recuperación|Sauvegardes et récupération
Backups include your songs, history, collections and settings.|Sicherungen enthalten Songs, Verlauf, Sammlungen und Einstellungen.|Las copias incluyen tus canciones, historial, colecciones y ajustes.|Les sauvegardes incluent vos chansons, historique, collections et paramètres.
Backup saved: {path}|Sicherung gespeichert: {path}|Copia guardada: {path}|Sauvegarde enregistrée : {path}
Create backup|Sicherung erstellen|Crear copia de seguridad|Créer une sauvegarde
Choose backup|Sicherung wählen|Elegir copia de seguridad|Choisir une sauvegarde
Import history.json|history.json importieren|Importar history.json|Importer history.json
Restore backup|Sicherung wiederherstellen|Restaurar copia de seguridad|Restaurer la sauvegarde
Replace the current library with this backup? A safety backup of the current library will be kept.|Aktuelle Bibliothek durch diese Sicherung ersetzen? Eine Sicherheitskopie der aktuellen Bibliothek bleibt erhalten.|¿Reemplazar la biblioteca actual con esta copia? Se conservará una copia de seguridad de la biblioteca actual.|Remplacer la bibliothèque actuelle par cette sauvegarde ? Une copie de sécurité de la bibliothèque actuelle sera conservée.
Imported {count} songs.|{count} Songs importiert.|Se importaron {count} canciones.|{count} chansons importées.
Import exported history|Exportierten Verlauf importieren|Importar historial exportado|Importer l'historique exporté
Restore backup…|Sicherung wiederherstellen…|Restaurar copia de seguridad…|Restaurer une sauvegarde…
Machine-perfect drums override human timing for drums; other instruments retain the selected feel.|Maschinenpräzises Schlagzeug ersetzt menschliches Timing beim Schlagzeug; andere Instrumente behalten das gewählte Spielgefühl.|La batería mecánica anula el ritmo humano de la batería; los demás instrumentos mantienen el estilo seleccionado.|La batterie mécanique remplace le timing humain de la batterie ; les autres instruments gardent le jeu sélectionné.
Loose drums override precise timing for drums; other instruments retain the selected feel.|Lockeres Schlagzeug ersetzt präzises Timing beim Schlagzeug; andere Instrumente behalten das gewählte Spielgefühl.|La batería suelta anula el ritmo preciso de la batería; los demás instrumentos mantienen el estilo seleccionado.|La batterie relâchée remplace le timing précis de la batterie ; les autres instruments gardent le jeu sélectionné.
'''
CATALOGUES = {code: {} for code in ['de', 'es', 'fr']}
for row in _ROWS.strip().splitlines():
    key, *values = row.split('|')
    for code, value in zip(CATALOGUES, values):
        CATALOGUES[code][key] = value
_language = 'en'


def system_language(env=None):
    env = os.environ if env is None else env
    base = env.get('LC_ALL') or env.get('LC_MESSAGES') or env.get('LANG') or 'en'
    if base in ('C', 'POSIX', 'C.UTF-8', 'C.utf8'):
        return 'en'
    candidates = (env.get('LANGUAGE', '') + ':' + base).split(':')
    for candidate in candidates:
        code = candidate.split('.')[0].split('_')[0].split('-')[0].lower()
        if code in ['en', *CATALOGUES]:
            return code
    return 'en'


def set_language(code):
    global _language
    _language = system_language() if code == 'system' else code


def t(message, **values):
    return CATALOGUES.get(_language, {}).get(message, message).format(**values)
