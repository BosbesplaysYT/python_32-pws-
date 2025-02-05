// Voorbeeld: polling in het wacht-scherm om te zien of de game gestart kan worden.
document.addEventListener("DOMContentLoaded", function() {
    if(document.getElementById('game-board') === null) {
        // Dit is geen spel scherm, maar mogelijk een wacht-scherm.
        // Je kunt hier regelmatig een verzoek sturen naar de server om te checken of de game klaar is.
        console.log("Wacht-scherm actief...");
    } else {
        // Initialiseer het spelbord en andere game logica.
        console.log("Game scherm actief...");
    }
});

document.addEventListener("DOMContentLoaded", function() {
    // Controleer of we op de wachtpagina zijn door te kijken naar de container
    const waitingContainer = document.getElementById("waiting-container");
    if (waitingContainer) {
        const gameCode = waitingContainer.dataset.gameCode;
        // Poll elke 3 seconden de server om te zien of de game klaar is
        const checkInterval = setInterval(() => {
            fetch(`/check_game/${gameCode}`)
                .then(response => response.json())
                .then(data => {
                    if (data.joined) {
                        clearInterval(checkInterval);
                        // Redirect naar de gamepagina zodra er een tegenstander is
                        window.location.href = `/setup/${gameCode}`;
                    }
                })
                .catch(error => console.error('Error bij het controleren van de game status:', error));
        }, 1000); // 1000 milliseconden = 1 seconden
    }
});

document.addEventListener("DOMContentLoaded", function() {
  const boardSize = 10;
  
  // Haal gemeenschappelijke data op (indien aanwezig)
  const container = document.querySelector('.container');
  const gameCode = container ? container.dataset.gameCode : null;
  const role = container ? container.dataset.role || 'creator' : null;

  // Socket.IO connectie (zoals je al had)
  let socket = null;
  if (gameCode) {
    socket = io();
    socket.emit('join', { game_code: gameCode });
    socket.on('message', function(msg) {
      console.log('Bericht ontvangen van server:', msg);
    });
    socket.on('both_ready', function(data) {
      if (data.redirect) {
        window.location.href = data.redirect;
      }
    });
  }
  
  // === Setup Fase: Schepen Neerzetten ===
  const setupBoard = document.getElementById("setup-board");
  if (setupBoard) {
    // Beschikbare schepen
    let availableShips = [
      { id: "ship1", length: 2, placed: false, positions: [] },
      { id: "ship2", length: 3, placed: false, positions: [] },
      { id: "ship3", length: 4, placed: false, positions: [] }
    ];
    let selectedShip = null;
    
    // Variabele voor oriëntatie: 'horizontal' of 'vertical'
    let orientation = 'horizontal';
    
    // Toggle-knop voor oriëntatie
    const toggleOrientationBtn = document.getElementById("toggle-orientation");
    if (toggleOrientationBtn) {
      toggleOrientationBtn.addEventListener("click", function() {
        orientation = (orientation === 'horizontal') ? 'vertical' : 'horizontal';
        toggleOrientationBtn.textContent = `Oriëntatie: ${orientation === 'horizontal' ? 'horizontaal' : 'verticaal'}`;
      });
    }
    
    // Bouw het grid
    setupBoard.innerHTML = "";
    for (let row = 0; row < boardSize; row++) {
      for (let col = 0; col < boardSize; col++) {
        const cell = document.createElement("div");
        cell.classList.add("cell");
        cell.dataset.row = row;
        cell.dataset.col = col;
        cell.addEventListener("click", function() {
          if (!selectedShip) {
            alert("Selecteer eerst een schip!");
            return;
          }
          const startRow = parseInt(cell.dataset.row);
          const startCol = parseInt(cell.dataset.col);
          let canPlace = true;
          let newPositions = [];
          
          // Controleer of er genoeg ruimte is, afhankelijk van de oriëntatie
          if (orientation === 'horizontal') {
            if (startCol + selectedShip.length > boardSize) {
              canPlace = false;
            } else {
              for (let i = 0; i < selectedShip.length; i++) {
                const targetCol = startCol + i;
                const targetSelector = `.cell[data-row='${startRow}'][data-col='${targetCol}']`;
                const targetCell = setupBoard.querySelector(targetSelector);
                if (targetCell && targetCell.classList.contains("ship")) {
                  canPlace = false;
                  break;
                }
                newPositions.push({ row: startRow, col: targetCol });
              }
            }
          } else { // verticale plaatsing
            if (startRow + selectedShip.length > boardSize) {
              canPlace = false;
            } else {
              for (let i = 0; i < selectedShip.length; i++) {
                const targetRow = startRow + i;
                const targetSelector = `.cell[data-row='${targetRow}'][data-col='${startCol}']`;
                const targetCell = setupBoard.querySelector(targetSelector);
                if (targetCell && targetCell.classList.contains("ship")) {
                  canPlace = false;
                  break;
                }
                newPositions.push({ row: targetRow, col: startCol });
              }
            }
          }
          
          if (!canPlace) {
            alert("Onvoldoende ruimte of overlapping!");
            return;
          }
          
          // Als het schip al geplaatst was, verwijder de oude plaatsing
          if (selectedShip.placed) {
            selectedShip.positions.forEach(pos => {
              const oldCell = setupBoard.querySelector(`.cell[data-row='${pos.row}'][data-col='${pos.col}']`);
              if (oldCell) oldCell.classList.remove("ship");
            });
          }
          
          // Plaats het schip op het bord
          newPositions.forEach(pos => {
            const targetCell = setupBoard.querySelector(`.cell[data-row='${pos.row}'][data-col='${pos.col}']`);
            if (targetCell) targetCell.classList.add("ship");
          });
          
          // Update het schip in availableShips
          selectedShip.placed = true;
          selectedShip.positions = newPositions;
          updateFinishButton();
        });
        setupBoard.appendChild(cell);
      }
    }
    
    // Verwerk de selectie van schepen via de knoppen
    const shipButtons = document.querySelectorAll(".ship-btn");
    shipButtons.forEach(btn => {
      btn.addEventListener("click", function() {
        shipButtons.forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        const shipId = btn.dataset.shipId;
        // Zorg ervoor dat de lengte ook wordt gebruikt (of gebruik de waarde uit availableShips)
        selectedShip = availableShips.find(ship => ship.id === shipId);
      });
    });
    
    // Update de “Klaar!” knop
    const finishBtn = document.getElementById("finishSetup");
    function updateFinishButton() {
      const allPlaced = availableShips.every(ship => ship.placed);
      finishBtn.disabled = !allPlaced;
    }
    finishBtn.addEventListener("click", function() {
      if (!availableShips.every(ship => ship.placed)) {
        alert("Plaats alle schepen eerst!");
        return;
      }
      // Stuur via socket dat deze speler klaar is, samen met de plaatsingsgegevens
      if (socket) {
        socket.emit('player_ready', { game_code: gameCode, role: role, shipPlacements: availableShips });
      }
      finishBtn.textContent = "Wachten op tegenstander...";
      finishBtn.disabled = true;
    });
  }
  
    // === Battle Fase: Twee Borden opbouwen ===

    let isMyTurn = false;  // Wordt later ingesteld via socket 'turn_change'

    const playerBoard = document.getElementById("player-board");
    const enemyBoard = document.getElementById("enemy-board");
    if (playerBoard && enemyBoard) {
      // Functie om een grid op te bouwen
      function createGrid(boardElement) {
        boardElement.innerHTML = "";
        for (let row = 0; row < boardSize; row++) {
          for (let col = 0; col < boardSize; col++) {
            const cell = document.createElement("div");
            cell.classList.add("cell");
            cell.dataset.row = row;
            cell.dataset.col = col;
            boardElement.appendChild(cell);
          }
        }
      }
      createGrid(playerBoard);
      createGrid(enemyBoard);
  
      // Voeg een klik-handler toe aan het vijandelijke bord om een schot af te vuren
      enemyBoard.addEventListener("click", function(e) {
        const cell = e.target;
        if (cell.classList.contains("cell") && !cell.classList.contains("shot")) {
          if (!isMyTurn) {
            alert("Wacht op je beurt!");
            return;
          }
          const row = parseInt(cell.dataset.row);
          const col = parseInt(cell.dataset.col);
          // Stuur het schot via Socket.IO
          socket.emit('fire_shot', { game_code: gameCode, row: row, col: col, role: role });
        }
      });

      // Ontvangt de uitkomst van een schot (hit of miss)
      socket.on('shot_result', function(data) {
        console.log(`Schot door ${data.shooter} op [${data.row}, ${data.col}]: ${data.result}`);
        if (data.shooter === role) {
          // Dit is jouw schot op het vijandelijke bord
          const enemyCell = enemyBoard.querySelector(`.cell[data-row='${data.row}'][data-col='${data.col}']`);
          if (enemyCell) {
            enemyCell.classList.add(data.result);  // voeg 'hit' of 'miss' toe als class
            enemyCell.textContent = data.result === 'hit' ? 'X' : 'O';
          }
        } else {
          // Dit is een schot van de tegenstander op jouw bord
          const playerBoard = document.getElementById("player-board");
          const playerCell = playerBoard.querySelector(`.cell[data-row='${data.row}'][data-col='${data.col}']`);
          if (playerCell) {
            playerCell.classList.add(data.result);
            playerCell.textContent = data.result === 'hit' ? 'X' : 'O';
          }
        }
      });

      // Update wie er aan de beurt is
      socket.on('turn_change', function(data) {
        isMyTurn = (data.current_turn === role);
        // Werk de UI bij (bijv. toon een bericht)
        const turnMessage = document.getElementById("turn-message");
        if (turnMessage) {
          turnMessage.textContent = isMyTurn ? "Jij bent aan de beurt" : "Wacht op tegenstander...";
        }
      });

    }
  });
  
  

