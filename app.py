from flask import Flask, request, jsonify, render_template
import random, string, time

app = Flask(__name__)

# Global in‑memory game store.
games = {}

def generate_game_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# --- Create Game ---
@app.route('/create', methods=['POST'])
def create_game():
    data = request.json
    player_name = data.get('playerName')
    if not player_name:
        return jsonify({"error": "Missing player name"}), 400
    
    game_code = generate_game_code()
    games[game_code] = {
        "players": {
            "player1": {
                "name": player_name,
                "ships": None,
                "hits": [],
                "misses": [],
                "incoming_misses": []  # NEW: For showing opponent’s missed shots briefly
            },
            "player2": None  # Will be set when another player joins.
        },
        "status": "waiting",  # waiting -> placing -> battle -> gameover
        "turn": None,
        "winner": None
    }
    return jsonify({"gameCode": game_code})

# --- Join Game ---
@app.route('/join', methods=['POST'])
def join_game():
    data = request.json
    player_name = data.get('playerName')
    game_code = data.get('gameCode')
    if not player_name or not game_code:
        return jsonify({"error": "Missing player name or game code"}), 400
    
    # Uppercase only the letters in the game code.
    game_code = ''.join(char.upper() if char.isalpha() else char for char in game_code)
    
    if game_code not in games:
        return jsonify({"error": "Invalid game code"}), 400
    
    game = games[game_code]
    if game["players"]["player2"] is not None:
        return jsonify({"error": "Game heeft al 2 spelers"}), 400
    
    game["players"]["player2"] = {
        "name": player_name,
        "ships": None,
        "hits": [],
        "misses": [],
        "incoming_misses": []  # NEW
    }
    # Both players are now connected; transition to the ship placement phase.
    game["status"] = "placing"
    return jsonify({"message": "Joined game", "gameCode": game_code})

# --- Place Ships ---
@app.route('/place_ships', methods=['POST'])
def place_ships():
    data = request.json
    game_code = data.get("gameCode")
    player = data.get("player")  # Expected to be "player1" or "player2"
    ships = data.get("ships")    # List of ship objects (with positions, etc.)
    
    if not game_code or not player or ships is None:
        return jsonify({"error": "Missing data"}), 400
    if game_code not in games:
        return jsonify({"error": "Invalid game code"}), 400
    
    # Add a "sunk" flag to each ship if not already provided.
    for ship in ships:
        if "sunk" not in ship:
            ship["sunk"] = False
    
    game = games[game_code]
    if player not in game["players"]:
        return jsonify({"error": "Invalid player"}), 400
    
    # Save the ship placements.
    game["players"][player]["ships"] = ships

    # If both players have placed their ships, transition to battle phase.
    p1_ships = game["players"]["player1"]["ships"]
    p2_ships = game["players"]["player2"]["ships"] if game["players"]["player2"] else None

    if p1_ships and p2_ships:
        game["status"] = "battle"
        # Randomly choose which player starts.
        game["turn"] = "player1" if random.random() < 0.5 else "player2"
    
    return jsonify({"message": "Ships placed", "status": game["status"]})

# --- Fire (Make a Move) ---
@app.route('/fire', methods=['POST'])
def fire():
    data = request.json
    game_code = data.get("gameCode")
    player = data.get("player")  # "player1" or "player2"
    x = data.get("x")
    y = data.get("y")
    
    if not game_code or not player or x is None or y is None:
        return jsonify({"error": "Missing data"}), 400
    if game_code not in games:
        return jsonify({"error": "Invalid game code"}), 400
    
    game = games[game_code]
    if game["status"] != "battle":
        return jsonify({"error": "Game is not in battle phase"}), 400

    if game["turn"] != player:
        return jsonify({"error": "Not your turn"}), 400

    opponent = "player1" if player == "player2" else "player2"
    opponent_ships = game["players"][opponent]["ships"]
    
    hit = False
    for ship in opponent_ships:
        # Each ship is a dict: {"positions": [[x1, y1], [x2, y2], ...]}
        if [x, y] in ship["positions"]:
            hit = True
            game["players"][player]["hits"].append([x, y])
            break
    if not hit:
        game["players"][player]["misses"].append([x, y])
        # NEW: Also record the miss on the defender’s record with a timestamp.
        game["players"][opponent]["incoming_misses"].append({"pos": [x, y], "timestamp": time.time()})
    
    # Check win condition: if every opponent ship cell has been hit.
    all_opponent_positions = []
    for ship in opponent_ships:
        all_opponent_positions.extend(ship["positions"])
    
    if all([pos in game["players"][player]["hits"] for pos in all_opponent_positions]):
        game["status"] = "gameover"
        game["winner"] = player

    # NEW: Check if a ship was sunk by this hit.
    sunk_ship = None
    if hit:
        for ship in opponent_ships:
            if not ship.get("sunk", False) and all(pos in game["players"][player]["hits"] for pos in ship["positions"]):
                ship["sunk"] = True
                sunk_ship = ship
                break
    else:
        # Change turn only if it was a miss.
        game["turn"] = opponent

    response = {
        "hit": hit,
        "status": game["status"],
        "turn": game["turn"],
        "winner": game["winner"],
        "sunk": sunk_ship  # Will be non-null if a ship was just sunk.
    }

    return jsonify(response)

# --- Get Game State (for polling) ---
@app.route('/game_state', methods=['GET'])
def game_state():
    game_code = request.args.get("gameCode")
    if not game_code or game_code not in games:
        return jsonify({"error": "Invalid game code"}), 400
    game = games[game_code]
    response = {
        "players": game["players"],
        "status": game["status"],
        "turn": game["turn"],
        "winner": game["winner"],
        "opponentJoined": game["players"]["player2"] is not None
    }
    return jsonify(response)

@app.route('/stop', methods=['POST'])
def stop():
    game_code = request.args.get("gameCode")
    if not game_code or game_code not in games:
        return jsonify({"error": "Invalid game code"}), 400
    
    del games[game_code]
    return jsonify({"message": f"Game {game_code} stopped"})

# --- Page Routes ---
@app.route('/setup')
def setup():
    return render_template('setup.html')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/battle')
def battle():
    return render_template('battle.html')

@app.route('/end')
def end():
    return render_template('end.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
