import json
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
import os
from datetime import datetime
from functools import wraps
import hashlib

app = Flask(__name__)
app.secret_key = "secret_key_vote_2025"

DATA_FILE = os.path.join(os.path.dirname(__file__), "donnees.json")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── Constantes Admin ───────────────────────────────────────────────────────
ADMIN_USERNAME = "Nathanael12"
ADMIN_PASSWORD_HASH = hashlib.sha256("Ose1233.".encode()).hexdigest()

# ─── Fonctions Utilitaires ───────────────────────────────────────────────────

def charger_donnees():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_donnees(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def verifier_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper

def verifier_electeur(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'electeur_id' not in session:
            return redirect(url_for('electeur_login'))
        return f(*args, **kwargs)
    return wrapper

def calculer_classement(data):
    """Calcule le classement automatique des candidats postulants"""
    comptage = {}
    for vote in data["votes"]:
        cid = vote["candidat_id"]
        comptage[cid] = comptage.get(cid, 0) + 1
    
    # Ajouter votes aux candidats postulés
    for candidat in data["candidats_postules"]:
        candidat['votes'] = comptage.get(candidat['id'], 0)


    
    # Trier par votes décroissants
    classement = sorted(data["candidats_postules"], key=lambda x: x['votes'], reverse=True)
    
    # Assigner les postes finaux
    resultats = []
    postes = ["CP", "CPA", "Secrétaire", "Chef de Sécurité"]
    
    for i, candidat in enumerate(classement[:4]):
        candidat['poste_final'] = postes[i] if i < 4 else None
        candidat['rang'] = i + 1
        resultats.append(candidat)
    
    return resultats


def est_eligible_pour_candidat(electeur, candidat):
    """Valide l'éligibilité d'un électeur pour un candidat donné."""
    electeur_promo = electeur.get('promotion', '').strip().upper()
    candidat_promo = candidat.get('promotion', '').strip().upper()
    electeur_filiere = electeur.get('filiere', '').strip().upper()
    candidat_filiere = candidat.get('filiere', '').strip().upper()

    # Rule 1: A student from BAC2 cannot vote for BAC1 candidates in the TECHNOLOGIE filière
    if electeur_promo == 'BAC2' and candidat_promo == 'BAC1' and candidat_filiere == 'TECHNOLOGIE':
        return False, "Un étudiant de BAC2 ne peut pas voter pour un candidat de BAC1 en Technologie."

    # Rule 2: A student from BAC IAGE cannot vote for a BAC1 Technologie candidate
    if 'IAGE' in electeur_filiere and candidat_promo == 'BAC1' and candidat_filiere == 'TECHNOLOGIE':
        return False, "Un étudiant de IAGE ne peut pas voter pour un candidat de BAC1 en Technologie."

    # Rule 3: BAC1 IA can vote for BAC1 GL, and vice versa
    if electeur_promo == 'BAC1' and candidat_promo == 'BAC1':
        if (electeur_filiere == 'IA' and candidat_filiere == 'GL') or (electeur_filiere == 'GL' and candidat_filiere == 'IA'):
            return True, ""

    # General rule: Otherwise, they must match promotion and filiere unless it's the specific exceptions above
    if electeur_promo != candidat_promo:
        return False, "Vous ne pouvez pas voter pour un candidat d'une autre promotion."

    if electeur_filiere != candidat_filiere:
        return False, f"Votre filière ({electeur_filiere}) ne vous permet pas de voter pour un candidat de la filière {candidat_filiere}."

    return True, ""

# ─── ROUTES ADMIN ───────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == ADMIN_USERNAME and hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH:
            session['admin_logged_in'] = True
            session['admin_name'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Identifiant ou mot de passe incorrect"
    
    return render_template('admin_login.html', error=error)

@app.route('/admin/dashboard')
@verifier_admin
def admin_dashboard():
    data = charger_donnees()
    
    nb_candidats = len(data['candidats_postules'])
    nb_electeurs = len(data['electeurs'])
    nb_votes = len(data['votes'])
    taux_participation = round((nb_votes / nb_electeurs * 100) if nb_electeurs > 0 else 0, 1)
    
    # Compter les votes par candidat
    comptage = {}
    for vote in data['votes']:
        cid = vote['candidat_id']
        comptage[cid] = comptage.get(cid, 0) + 1
    
    # Ajouter le nombre de votes à chaque candidat
    for candidat in data['candidats_postules']:
        candidat['votes'] = comptage.get(candidat['id'], 0)
    
    # Vérifier quels électeurs ont voté
    electeurs_votes = set(vote['electeur_id'] for vote in data['votes'])
    for electeur in data['electeurs']:
        electeur['has_voted'] = electeur['id'] in electeurs_votes
        
    # Calculer la répartition des votes par filière
    filiere_votes = {}
    for vote in data['votes']:
        electeur = next((e for e in data['electeurs'] if e['id'] == vote['electeur_id']), None)
        if electeur:
            fil = electeur.get('filiere', 'Autre')
            filiere_votes[fil] = filiere_votes.get(fil, 0) + 1
            
    # Extraire les derniers votes (top 5 par timestamp décroissant)
    derniers_votes = []
    votes_tries = sorted(data['votes'], key=lambda x: x.get('timestamp', ''), reverse=True)
    for v in votes_tries[:5]:
        electeur = next((e for e in data['electeurs'] if e['id'] == v['electeur_id']), None)
        candidat = next((c for c in data['candidats_postules'] if c['id'] == v['candidat_id']), None)
        if electeur and candidat:
            try:
                dt = datetime.fromisoformat(v.get('timestamp', ''))
                heure_str = dt.strftime('%H:%M')
            except:
                heure_str = "Récemment"
            derniers_votes.append({
                'electeur_nom': f"{electeur['prenom']} {electeur['nom']}",
                'candidat_nom': candidat['nom_complet'],
                'heure': heure_str
            })
    
    return render_template('admin_dashboard.html',
        nb_candidats=nb_candidats,
        nb_electeurs=nb_electeurs,
        nb_votes=nb_votes,
        taux_participation=taux_participation,
        candidats_postules=data['candidats_postules'],
        electeurs=data['electeurs'],
        resultats_publies=data.get('resultats_publies', False),
        filiere_votes=filiere_votes,
        derniers_votes=derniers_votes
    )

@app.route('/admin/candidat-add', methods=['POST'])
@verifier_admin
def admin_candidat_add():
    data = charger_donnees()
    
    nom_complet = request.form.get('nom_complet', '').strip()
    matricule = request.form.get('matricule', '').strip()
    promotion = request.form.get('promotion', '').strip()
    poste_sollicite = request.form.get('poste_sollicite', '').strip()
    description = request.form.get('description', '').strip()
    filiere_groupe = request.form.get('filiere_groupe', '').strip()
    
    # Validation
    if not all([nom_complet, matricule, promotion, poste_sollicite, description]):
        return redirect(url_for('admin_dashboard'))
    
    # Vérifier si délégué général et si BAC3+
    if poste_sollicite == 'Délégué Général':
        if 'BAC3' not in promotion and 'BAC4' not in promotion:
            flash('Le Délégué Général doit être au moins en BAC3', 'error')
            return redirect(url_for('admin_dashboard'))
    
    # Créer le candidat
    new_id = max((c['id'] for c in data['candidats_postules']), default=0) + 1
    photo_path = None
    
    if 'photo' in request.files and request.files['photo'].filename:
        file = request.files['photo']
        filename = f"candidat_{new_id}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        photo_path = f"/static/uploads/{filename}"
    
    candidat = {
        'id': new_id,
        'nom_complet': nom_complet,
        'matricule': matricule,
        'photo': photo_path,
        'promotion': promotion,
        'filiere': filiere_groupe,
        'poste_sollicite': poste_sollicite,
        'description': description,
        'votes': 0,
        'date_inscription': datetime.now().isoformat()
    }
    
    data['candidats_postules'].append(candidat)
    sauvegarder_donnees(data)
    
    return redirect(url_for('admin_dashboard') + '#candidats')

@app.route('/admin/electeur-add', methods=['POST'])
@verifier_admin
def admin_electeur_add():
    data = charger_donnees()
    
    nom = request.form.get('nom', '').strip()
    postnom = request.form.get('postnom', '').strip()
    prenom = request.form.get('prenom', '').strip()
    matricule = request.form.get('matricule', '').strip()
    promotion = request.form.get('promotion', '').strip()
    filiere = request.form.get('filiere', '').strip()
    
    if not all([nom, postnom, prenom, matricule, promotion, filiere]):
        return redirect(url_for('admin_dashboard'))
    
    # Vérifier si le matricule existe déjà
    if any(e['matricule'] == matricule for e in data['electeurs']):
        flash('Ce matricule existe déjà', 'error')
        return redirect(url_for('admin_dashboard'))
    
    new_id = max((e['id'] for e in data['electeurs']), default=0) + 1
    
    electeur = {
        'id': new_id,
        'nom': nom,
        'postnom': postnom,
        'prenom': prenom,
        'matricule': matricule,
        'promotion': promotion,
        'filiere': filiere,
        'date_inscription': datetime.now().isoformat()
    }
    
    data['electeurs'].append(electeur)
    sauvegarder_donnees(data)
    
    return redirect(url_for('admin_dashboard') + '#electeurs')

@app.route('/admin/electeur-delete/<int:electeur_id>', methods=['POST'])
@verifier_admin
def admin_electeur_delete(electeur_id):
    data = charger_donnees()
    data['electeurs'] = [e for e in data['electeurs'] if e['id'] != electeur_id]
    data['votes'] = [v for v in data['votes'] if v['electeur_id'] != electeur_id]
    sauvegarder_donnees(data)
    flash('Électeur supprimé avec succès', 'success')
    return redirect(url_for('admin_dashboard') + '#electeurs')

@app.route('/admin/candidat-delete/<int:candidat_id>', methods=['POST'])
@verifier_admin
def admin_candidat_delete(candidat_id):
    data = charger_donnees()
    data['candidats_postules'] = [c for c in data['candidats_postules'] if c['id'] != candidat_id]
    data['votes'] = [v for v in data['votes'] if v['candidat_id'] != candidat_id]
    sauvegarder_donnees(data)
    flash('Candidat supprimé avec succès', 'success')
    return redirect(url_for('admin_dashboard') + '#candidats')

@app.route('/admin/electeur-edit/<int:electeur_id>', methods=['POST'])
@verifier_admin
def admin_electeur_edit(electeur_id):
    data = charger_donnees()
    for e in data['electeurs']:
        if e['id'] == electeur_id:
            e['nom'] = request.form.get('nom', e['nom']).strip()
            e['postnom'] = request.form.get('postnom', e['postnom']).strip()
            e['prenom'] = request.form.get('prenom', e['prenom']).strip()
            e['matricule'] = request.form.get('matricule', e['matricule']).strip()
            e['promotion'] = request.form.get('promotion', e['promotion']).strip()
            e['filiere'] = request.form.get('filiere', e['filiere']).strip()
            break
    sauvegarder_donnees(data)
    flash('Électeur modifié', 'success')
    return redirect(url_for('admin_dashboard') + '#electeurs')

@app.route('/admin/candidat-edit/<int:candidat_id>', methods=['POST'])
@verifier_admin
def admin_candidat_edit(candidat_id):
    data = charger_donnees()
    for c in data['candidats_postules']:
        if c['id'] == candidat_id:
            c['nom_complet'] = request.form.get('nom_complet', c['nom_complet']).strip()
            c['matricule'] = request.form.get('matricule', c['matricule']).strip()
            c['promotion'] = request.form.get('promotion', c['promotion']).strip()
            c['poste_sollicite'] = request.form.get('poste_sollicite', c['poste_sollicite']).strip()
            c['filiere'] = request.form.get('filiere_groupe', c.get('filiere', '')).strip()
            c['description'] = request.form.get('description', c.get('description', '')).strip()
            
            if 'photo' in request.files and request.files['photo'].filename:
                file = request.files['photo']
                filename = f"candidat_{candidat_id}_{file.filename}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                c['photo'] = f"/static/uploads/{filename}"
            break
    sauvegarder_donnees(data)
    flash('Candidat modifié', 'success')
    return redirect(url_for('admin_dashboard') + '#candidats')

@app.route('/admin/publier-resultats', methods=['POST'])
@verifier_admin
def admin_publier_resultats():
    data = charger_donnees()
    
    if len(data['votes']) == 0:
        flash('Aucun vote enregistré', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Calculer le classement
    classement = calculer_classement(data)
    
    data['resultats_publies'] = True
    data['classement_final'] = classement
    sauvegarder_donnees(data)
    
    flash('Résultats publiés avec succès!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reinitialiser-resultats', methods=['POST'])
@verifier_admin
def admin_reinitialiser_resultats():
    data = charger_donnees()
    
    data['resultats_publies'] = False
    data['classement_final'] = []
    data['votes'] = []
    
    sauvegarder_donnees(data)
    
    flash('Résultats réinitialisés', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

# ─── ROUTES ÉLECTEURS (Mobile Interface) ──────────────────────────────────

@app.route('/')
def index():
    # Rediriger par défaut vers la page de connexion mobile
    return redirect(url_for('voter_login_mobile'))

# ─── ROUTES ÉLECTEURS - MOBILE (New Interface) ──────────────────────────────

@app.route('/voter/login', methods=['GET', 'POST'])
def voter_login_mobile():
    """Login mobile simplifié - Matricule uniquement"""
    error = None
    if request.method == 'POST':
        matricule = request.form.get('matricule', '').strip().upper()
        
        if not matricule:
            error = "Veuillez entrer votre matricule"
        else:
            data = charger_donnees()
            
            # Chercher l'électeur par matricule
            electeur = next((e for e in data['electeurs'] if e['matricule'] == matricule), None)
            
            if not electeur:
                error = "Matricule non enregistré. Contactez l'administrateur"
            else:
                # Connecter l'électeur (même s'il a déjà voté)
                session['electeur_id'] = electeur['id']
                session['electeur_nom'] = f"{electeur['prenom']} {electeur['nom']}"
                session['matricule'] = matricule
                session['promotion'] = electeur['promotion']
                session['filiere'] = electeur['filiere']
                return redirect(url_for('voter_mobile'))
    
    return render_template('voter_login.html', error=error)

@app.route('/voter')
@app.route('/voter_mobile')
def voter_mobile():
    """Interface de vote mobile - Candidats filtrés par promotion"""
    if 'electeur_id' not in session:
        return redirect(url_for('voter_login_mobile'))
    
    data = charger_donnees()
    electeur_id = session['electeur_id']
    promotion = session.get('promotion', '')
    
    # Récupérer les données de l'électeur
    electeur = next((e for e in data['electeurs'] if e['id'] == electeur_id), None)
    if not electeur:
        session.clear()
        return redirect(url_for('voter_login_mobile'))
    
    # Vérifier si l'étudiant a déjà voté
    a_vote = any(v['electeur_id'] == electeur_id for v in data['votes'])
    voted_candidat_id = next((v['candidat_id'] for v in data['votes'] if v['electeur_id'] == electeur_id), None)
    
    # Filtrer les candidats de la même promotion
    candidats_filtres = [c for c in data['candidats_postules'] if c['promotion'] == promotion]
    
    return render_template('voter_mobile.html',
        candidats=candidats_filtres,
        electeur_nom=session.get('electeur_nom', 'Électeur'),
        promotion=promotion,
        filiere=session.get('filiere', ''),
        a_vote=a_vote,
        voted_candidat_id=voted_candidat_id
    )

@app.route('/resultats-mobile')
def resultats_mobile():
    """Interface de résultats mobile"""
    if 'electeur_id' not in session:
        return redirect(url_for('voter_login_mobile'))
    
    data = charger_donnees()
    electeur_id = session['electeur_id']
    a_vote = any(v['electeur_id'] == electeur_id for v in data['votes'])
    
    if data.get('resultats_publies'):
        classement = data.get('classement_final', [])
        return render_template('resultats_mobile.html',
            classement=classement,
            a_vote=a_vote
        )
    else:
        return render_template('resultats_mobile.html',
            classement=[],
            a_vote=a_vote
        )

@app.route('/notifications-mobile')
@verifier_electeur
def notifications_mobile():
    """Interface de notifications mobile"""
    return render_template('notifications_mobile.html')

@app.route('/settings-mobile')
@verifier_electeur
def settings_mobile():
    """Interface des paramètres mobile"""
    return render_template('settings_mobile.html')

@app.route('/api/verify-matricule', methods=['POST'])
def api_verify_matricule():
    """API pour vérifier le matricule"""
    data_req = request.get_json()
    matricule = data_req.get('matricule', '').strip().upper()
    
    data = charger_donnees()
    electeur = next((e for e in data['electeurs'] if e['matricule'] == matricule), None)
    
    if not electeur:
        return jsonify({'success': False, 'error': 'Matricule non reconnu'})
    
    # Vérifier s'il a déjà voté
    a_vote = any(v['electeur_id'] == electeur['id'] for v in data['votes'])
    if a_vote:
        return jsonify({'success': False, 'error': 'Vous avez déjà voté'})
    
    return jsonify({'success': True, 'data': electeur})

# ─── ROUTES ÉLECTEURS (Legacy Desktop Interface) ────────────────────────────

@app.route('/electeur/login', methods=['GET', 'POST'])
def electeur_login():
    error = None
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        postnom = request.form.get('postnom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        matricule = request.form.get('matricule', '').strip()
        promotion = request.form.get('promotion', '').strip()
        filiere = request.form.get('filiere', '').strip()
        
        if not all([nom, postnom, prenom, matricule, promotion, filiere]):
            error = "Veuillez remplir tous les champs"
        else:
            data = charger_donnees()
            
            # Chercher l'électeur par matricule
            electeur = next((e for e in data['electeurs'] if e['matricule'] == matricule), None)
            
            if not electeur:
                error = "Matricule non enregistré. Contactez l'administrateur"
            else:
                session['electeur_id'] = electeur['id']
                session['electeur_nom'] = f"{prenom} {nom}"
                session['matricule'] = matricule
                return redirect(url_for('dashboard'))
    
    return render_template('login.html', error=error)

@app.route('/dashboard')
@verifier_electeur
def dashboard():
    data = charger_donnees()
    electeur_id = session['electeur_id']
    a_vote = any(v['electeur_id'] == electeur_id for v in data['votes'])
    
    # Si résultats publiés, afficher le classement final
    if data.get('resultats_publies'):
        classement = data.get('classement_final', [])
        return render_template('dashboard_resultats.html',
            classement=classement,
            electeur_nom=session.get('electeur_nom', 'Électeur'),
            a_vote=a_vote
        )
    
    # Sinon, afficher l'interface de vote
    nb_electeurs = len(data['electeurs'])
    nb_votes = len(data['votes'])
    taux_participation = round((nb_votes / nb_electeurs * 100) if nb_electeurs > 0 else 0, 1)
    
    comptage = {}
    for vote in data['votes']:
        cid = vote['candidat_id']
        comptage[cid] = comptage.get(cid, 0) + 1
    
    resultats_candidats = []
    for candidat in data['candidats_postules']:
        nb = comptage.get(candidat['id'], 0)
        pct = round((nb / nb_votes * 100) if nb_votes > 0 else 0, 1)
        resultats_candidats.append({**candidat, 'nb_votes': nb, 'pourcentage': pct})
    
    resultats_candidats.sort(key=lambda x: x['nb_votes'], reverse=True)
    
    return render_template('dashboard.html',
        etudiant_nom=session.get('electeur_nom', 'Électeur'),
        a_vote=a_vote,
        total_etudiants=nb_electeurs,
        total_votes=nb_votes,
        total_candidats=len(data['candidats_postules']),
        taux_participation=taux_participation,
        candidats=data['candidats_postules'],
        resultats_candidats=resultats_candidats
    )

@app.route('/candidats')
@verifier_electeur
def candidats():
    data = charger_donnees()
    electeur_id = session['electeur_id']
    a_vote = any(v['electeur_id'] == electeur_id for v in data['votes'])
    
    return render_template('candidats.html',
        candidats=data['candidats_postules'],
        a_vote=a_vote,
        electeur_nom=session.get('electeur_nom', 'Électeur')
    )

@app.route('/vote', methods=['POST'])
@verifier_electeur
def vote():
    data = charger_donnees()
    electeur_id = session['electeur_id']
    candidat_id = int(request.form.get('candidat_id'))
    
    # Vérifier que l'électeur n'a pas déjà voté
    if any(v['electeur_id'] == electeur_id for v in data['votes']):
        return redirect(url_for('voter_mobile') if 'promotion' in session else url_for('candidats'))
    
    # Vérifier que le candidat existe
    candidat = next((c for c in data['candidats_postules'] if c['id'] == candidat_id), None)
    if not candidat:
        return redirect(url_for('voter_mobile') if 'promotion' in session else url_for('candidats'))
    
    # Vérifier que l'électeur n'est pas un candidat postulant
    if any(c['matricule'] == session.get('matricule') for c in data['candidats_postules']):
        flash("Les candidats ne peuvent pas voter", 'error')
        return redirect(url_for('voter_mobile') if 'promotion' in session else url_for('candidats'))

    # Valider la promotion et la filière de l'électeur contre le candidat
    electeur = next((e for e in data['electeurs'] if e['id'] == electeur_id), None)
    if not electeur:
        session.clear()
        return redirect(url_for('voter_login_mobile'))

    eligible, reason = est_eligible_pour_candidat(electeur, candidat)
    if not eligible:
        flash(reason, 'error')
        return redirect(url_for('voter_mobile'))

    # Enregistrer le vote
    data['votes'].append({
        'electeur_id': electeur_id,
        'candidat_id': candidat_id,
        'timestamp': datetime.now().isoformat()
    })
    sauvegarder_donnees(data)
    
    # Rediriger en fonction de l'interface
    if 'promotion' in session:
        return redirect(url_for('resultats_mobile'))
    else:
        return redirect(url_for('candidats'))

@app.route('/resultats')
@verifier_electeur
def resultats():
    data = charger_donnees()
    
    if 'promotion' in session:
        # Mobile interface
        return redirect(url_for('resultats_mobile'))
    else:
        # Desktop interface
        if data.get('resultats_publies'):
            classement = data.get('classement_final', [])
            return render_template('resultats_finaux.html', classement=classement)
        else:
            return render_template('resultats_en_attente.html')

@app.route('/electeur/logout')
def electeur_logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/voter/logout')
def voter_logout():
    session.clear()
    return redirect(url_for('voter_login_mobile'))

@app.route('/login')
def login():
    return redirect(url_for('electeur_login'))

# ─── API ───────────────────────────────────────────────────────────

@app.route('/api/stats')
@verifier_electeur
def api_stats():
    data = charger_donnees()
    electeur_id = session['electeur_id']
    
    nb_votes = len(data['votes'])
    nb_electeurs = len(data['electeurs'])
    
    comptage = {}
    for vote in data['votes']:
        cid = vote['candidat_id']
        comptage[cid] = comptage.get(cid, 0) + 1
    
    candidats_data = []
    for c in data['candidats_postules']:
        nb = comptage.get(c['id'], 0)
        pct = round((nb / nb_votes * 100) if nb_votes > 0 else 0, 1)
        candidats_data.append({'nom': c['nom_complet'], 'votes': nb, 'pct': pct})
    
    candidats_data.sort(key=lambda x: x['votes'], reverse=True)
    
    return jsonify({
        'total_votes': nb_votes,
        'total_electeurs': nb_electeurs,
        'taux': round((nb_votes / nb_electeurs * 100) if nb_electeurs > 0 else 0, 1),
        'candidats': candidats_data
    })

# ─── Run ───────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)