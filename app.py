import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g, flash, jsonify
import uuid
import os
from flask_socketio import SocketIO, emit, join_room
import json

# Pad naar de database
DATABASE = os.path.join(os.path.dirname(__file__), 'zeeslag.db')

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Vervang dit in productie door een veilige sleutel

# Initialiseer SocketIO
socketio = SocketIO(app)

games_ready = {}

game_states = {}

# Hulpfunctie om de databaseverbinding per request te openen
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

# Initialiseer de database (maak tabellen als ze nog niet bestaan)
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Tabel voor games
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_code TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Tabel voor spelers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                role TEXT,  -- 'creator' of 'joiner'
                ship_positions TEXT,
                FOREIGN KEY (game_id) REFERENCES games(id)
            )
        ''')
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Routes voor de spel flow (startpagina, create_game, join_game, enter_name, waiting, game, end)
@app.route('/')
def start():
    return render_template('start.html')

@app.route('/create_game', methods=['POST'])
def create_game():
    game_code = str(uuid.uuid4())[:6].upper()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('INSERT INTO games (game_code) VALUES (?)', (game_code,))
        db.commit()
    except sqlite3.IntegrityError:
        flash('Fout bij het aanmaken van de game, probeer het opnieuw.')
        return redirect(url_for('start'))
    return redirect(url_for('enter_name', game_code=game_code, role='creator'))

@app.route('/join_game', methods=['POST'])
def join_game():
    game_code = request.form.get('game_code', '').upper()
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM games WHERE game_code = ?', (game_code,))
    game = cursor.fetchone()
    if game is None:
        flash('Game niet gevonden, controleer de game code.')
        return redirect(url_for('start'))
    return redirect(url_for('enter_name', game_code=game_code, role='joiner'))

@app.route('/enter_name/<game_code>/<role>', methods=['GET', 'POST'])
def enter_name(game_code, role):
    if request.method == 'POST':
        player_name = request.form.get('player_name')
        if not player_name:
            flash('Vul alstublieft een naam in.')
            return redirect(request.url)
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM games WHERE game_code = ?', (game_code,))
        game = cursor.fetchone()
        if game is None:
            flash('Game niet gevonden.')
            return redirect(url_for('start'))
        game_id = game['id']
        cursor.execute('INSERT INTO players (game_id, player_name, role) VALUES (?, ?, ?)', (game_id, player_name, role))
        db.commit()
        if role == 'creator':
            return redirect(url_for('waiting', game_code=game_code))
        else:
            # Voeg de role toe aan de redirect URL
            return redirect(url_for('setup', game_code=game_code, role=role))
    return render_template('enter_name.html', game_code=game_code, role=role)

@app.route('/waiting/<game_code>')
def waiting(game_code):
    return render_template('waiting.html', game_code=game_code)

@app.route('/setup/<game_code>')
def setup(game_code):
    # Haal de role op uit de query parameters
    role = request.args.get('role', 'creator')
    return render_template('setup.html', game_code=game_code, role=role)

@app.route('/battle/<game_code>')
def battle(game_code):
    # Render de battle template met de game_code
    return render_template('battle.html', game_code=game_code)


@app.route('/end/<game_code>')
def end(game_code):
    result = "gewonnen"  # Placeholder voor de uitslag
    return render_template('end.html', game_code=game_code, result=result)

@app.route('/check_game/<game_code>')
def check_game(game_code):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM games WHERE game_code = ?", (game_code,))
    game = cursor.fetchone()
    if not game:
        return jsonify({"joined": False})
    game_id = game['id']
    cursor.execute("SELECT COUNT(*) as player_count FROM players WHERE game_id = ?", (game_id,))
    data = cursor.fetchone()
    player_count = data["player_count"] if data else 0
    if player_count >= 2:
        return jsonify({"joined": True})
    return jsonify({"joined": False})

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit('message', {'data': 'Connectie geslaagd!'})

@socketio.on('join')
def on_join(data):
    game_code = data.get('game_code')
    if game_code:
        join_room(game_code)
        print(f"Client is toegetreden tot kamer: {game_code}")
        emit('message', {'data': f'Je bent toegevoegd aan kamer: {game_code}'}, room=game_code)

@socketio.on('test_message')
def handle_test_message(data):
    game_code = data.get('game_code')
    message = data.get('message')
    if game_code and message:
        # Verstuur het bericht naar iedereen in de kamer behalve de afzender
        emit('message', {'data': message}, room=game_code, include_self=False)
        print(f"Testbericht verstuurd in kamer {game_code}: {message}")

@socketio.on('player_ready')
def handle_player_ready(data):
    game_code = data.get('game_code')
    role = data.get('role')  # 'creator' of 'joiner'
    shipPlacements = data.get('shipPlacements')  # De plaatsingsgegevens

    if not game_code or not role:
        return

    db = get_db()
    cursor = db.cursor()
    # Haal het spel op
    cursor.execute('SELECT id FROM games WHERE game_code = ?', (game_code,))
    game = cursor.fetchone()
    if not game:
        return
    game_id = game['id']

    # Haal de speler op
    cursor.execute('SELECT id FROM players WHERE game_id = ? AND role = ?', (game_id, role))
    player = cursor.fetchone()
    if player:
        player_id = player['id']
        # Sla de scheepsposities op als JSON-string
        ship_positions_json = json.dumps(shipPlacements)
        cursor.execute('UPDATE players SET ship_positions = ? WHERE id = ?', (ship_positions_json, player_id))
        db.commit()

    # Houd bij of de speler klaar is (zoals eerder)
    if game_code not in games_ready:
        games_ready[game_code] = {'creator': False, 'joiner': False}
    games_ready[game_code][role] = True

    print(f"Speler {role} in game {game_code} is klaar en heeft schepen geplaatst: {shipPlacements}")

    if games_ready[game_code]['creator'] and games_ready[game_code]['joiner']:
        emit('both_ready', {'redirect': f'/battle/{game_code}'}, room=game_code)


@socketio.on('start_battle')
def handle_start_battle(data):
    """
    Start de battle-fase door de initiele turn vast te leggen.
    We nemen bijvoorbeeld aan dat de 'creator' mag beginnen.
    """
    game_code = data.get('game_code')
    if game_code:
        game_states[game_code] = {
            'current_turn': 'creator',
            # Hier kun je ook de overgebleven schipcellen per speler opslaan.
            # Voor nu laten we dit weg; we gaan alleen hit/miss checken.
        }
        # Informeer beide spelers wie er als eerste aan de beurt is:
        emit('turn_change', {'current_turn': 'creator'}, room=game_code)

@socketio.on('fire_shot')
def handle_fire_shot(data):
    """
    Ontvangt een schot van een speler en bepaalt of dit raak is.
    """
    game_code = data.get('game_code')
    row = data.get('row')
    col = data.get('col')
    shooter = data.get('role')  # 'creator' of 'joiner'

    # Controleer of we de battle state kennen
    state = game_states.get(game_code)
    if not state:
        return

    # Check of het echt de beurt is van de shooter:
    if state['current_turn'] != shooter:
        emit('error', {'message': 'Het is niet jouw beurt!'})
        return

    # Bepaal de tegenstander
    opponent = 'creator' if shooter == 'joiner' else 'joiner'

    # Haal de tegenstander zijn schip plaatsingen op (opgeslagen in de DB)
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id FROM games WHERE game_code = ?', (game_code,))
    game = cursor.fetchone()
    if not game:
        return
    game_id = game['id']
    cursor.execute('SELECT ship_positions FROM players WHERE game_id = ? AND role = ?', (game_id, opponent))
    opp_data = cursor.fetchone()
    if not opp_data:
        return

    # We verwachten dat ship_positions een JSON-string is waarin per schip een object met 'positions' staat.
    try:
        ship_positions = json.loads(opp_data['ship_positions'] or '[]')
    except Exception as e:
        ship_positions = []

    hit = False
    # Loop door alle schepen en hun posities om te kijken of het schot raak is.
    for ship in ship_positions:
        # Neem aan dat ieder schip-object er als volgt uitziet: { "id": "ship1", "length": 2, "positions": [{row:0, col:1}, ...] }
        for pos in ship.get('positions', []):
            if pos['row'] == row and pos['col'] == col:
                hit = True
                # (Optioneel: markeer deze positie als geraakt zodat herhaald schieten hier geen effect heeft)
                break
        if hit:
            break

    shot_result = 'hit' if hit else 'miss'

    # Informeer beide spelers over het resultaat
    emit('shot_result', {
        'shooter': shooter,
        'row': row,
        'col': col,
        'result': shot_result
    }, room=game_code)

    # Wissel de beurt naar de tegenstander
    state['current_turn'] = opponent
    emit('turn_change', {'current_turn': opponent}, room=game_code)

    # (Later: Controleer of alle schepen van de tegenstander volledig zijn geraakt, en zo ja, stuur een game over event)


# Zorg dat wanneer een client connect en zich aansluit, deze aan de room (game_code) wordt toegevoegd:
@socketio.on('join')
def on_join(data):
    game_code = data.get('game_code')
    if game_code:
        join_room(game_code)
        print(f"Client is toegetreden tot kamer: {game_code}")
        emit('message', {'data': f'Je bent toegevoegd aan kamer: {game_code}'}, room=game_code)

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True)
