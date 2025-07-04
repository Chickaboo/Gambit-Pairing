from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List, Tuple, Optional

from core.player import Player
from core.constants import RESULT_WHITE_WIN, RESULT_DRAW, RESULT_BLACK_WIN, WIN_SCORE, DRAW_SCORE, LOSS_SCORE, BYE_SCORE
from .dialogs import ManualPairDialog
import logging


class CheckableButton(QtWidgets.QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCheckable(True)
        self.check_char = "✓"
        self.setProperty("class", "ResultSelectorButton")

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            
            # Draw checkmark in the top-right corner
            painter.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
            font = QtGui.QFont(painter.font())
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            
            rect = self.rect()
            checkmark_rect = QtCore.QRect(rect.right() - 15, rect.top() + 2, 12, 12)
            painter.drawText(checkmark_rect, Qt.AlignmentFlag.AlignCenter, self.check_char)


class ResultSelector(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self.button_group = QtWidgets.QButtonGroup(self)
        self.button_group.setExclusive(True)

        # Create buttons with clear, readable labels
        self.btn_white_win = CheckableButton("1-0")
        self.btn_white_win.setProperty("result_const", RESULT_WHITE_WIN)
        self.btn_white_win.setToolTip("White wins")

        self.btn_draw = CheckableButton("½-½")
        self.btn_draw.setProperty("result_const", RESULT_DRAW)
        self.btn_draw.setToolTip("Draw")

        self.btn_black_win = CheckableButton("0-1")
        self.btn_black_win.setProperty("result_const", RESULT_BLACK_WIN)
        self.btn_black_win.setToolTip("Black wins")

        buttons = [self.btn_white_win, self.btn_draw, self.btn_black_win]
        for btn in buttons:
            self.button_group.addButton(btn)
            layout.addWidget(btn)
        
        layout.addStretch()  # Add stretch to prevent buttons from expanding too much

    def selectedResult(self) -> str:
        checked_button = self.button_group.checkedButton()
        return checked_button.property("result_const") if checked_button else ""

    def setResult(self, result_constant: str):
        for button in self.button_group.buttons():
            if button.property("result_const") == result_constant:
                button.setChecked(True)
                return
        # If no match, clear selection
        checked_button = self.button_group.checkedButton()
        if checked_button:
            self.button_group.setExclusive(False)
            checked_button.setChecked(False)
            self.button_group.setExclusive(True)


class TournamentTab(QtWidgets.QWidget):
    status_message = pyqtSignal(str)
    history_message = pyqtSignal(str)
    dirty = pyqtSignal()
    round_completed = pyqtSignal(int)
    standings_update_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tournament = None
        self.current_round_index = 0
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Header Layout
        header_layout = QtWidgets.QHBoxLayout()
        self.lbl_round_title = QtWidgets.QLabel("No Tournament Loaded")
        font = self.lbl_round_title.font()
        font.setPointSize(14)
        font.setBold(True)
        self.lbl_round_title.setFont(font)
        header_layout.addWidget(self.lbl_round_title)
        header_layout.addStretch()
        self.btn_print_pairings = QtWidgets.QPushButton(" Print Pairings")
        self.btn_print_pairings.setIcon(QtGui.QIcon.fromTheme("document-print"))
        self.btn_print_pairings.setToolTip("Print the current round\'s pairings")
        self.btn_print_pairings.setStyleSheet("padding: 5px;")
        header_layout.addWidget(self.btn_print_pairings)
        self.main_layout.addLayout(header_layout)        # Pairings Table - Reduced to 3 columns
        self.table_pairings = QtWidgets.QTableWidget(0, 3)
        self.table_pairings.setHorizontalHeaderLabels(["White", "Black", "Result"])
        self.table_pairings.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table_pairings.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table_pairings.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.table_pairings.setColumnWidth(2, 180) # Give enough space for the improved result selector
        self.table_pairings.verticalHeader().setVisible(False)
        self.table_pairings.setAlternatingRowColors(True)
        self.table_pairings.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Add context menu for manual adjustments
        self.table_pairings.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_pairings.customContextMenuRequested.connect(self.show_pairing_context_menu)

        self.main_layout.addWidget(self.table_pairings)

        # Bye Label
        self.lbl_bye = QtWidgets.QLabel("Bye: None")
        self.main_layout.addWidget(self.lbl_bye)

        # Set initial UI state
        self.update_ui_state()

        self.btn_print_pairings.clicked.connect(self.print_pairings)

    def set_tournament(self, tournament):
        self.tournament = tournament
        self.update_ui_state()

    def set_current_round_index(self, idx):
        self.current_round_index = idx
        self.update_ui_state()

    def start_tournament(self) -> None:
        if not self.tournament:
            QtWidgets.QMessageBox.warning(self, "Start Error", "No tournament loaded.")
            return
        if len(self.tournament.players) < 2:
            QtWidgets.QMessageBox.warning(self, "Start Error", "Add at least two players.")
            return
        # New minimum players check based on the number of rounds
        min_players = 2 ** self.tournament.num_rounds
        if len(self.tournament.players) < min_players:
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Insufficient Players",
                f"For a {self.tournament.num_rounds}-round tournament, a minimum of {min_players} players is recommended. The tournament may not work properly. Do you want to continue anyway?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Start Tournament",
            f"Start a {self.tournament.num_rounds}-round tournament with {len(self.tournament.players)} players?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        # Use current_round_index (starting at 0 for Round 1)
        if self.current_round_index >= self.tournament.num_rounds:
             QtWidgets.QMessageBox.information(self,"Tournament End", "All tournament rounds have been generated and processed.")
             self.update_ui_state(); return
        
        # Check if pairings for the current round already exist
        if self.current_round_index < len(self.tournament.rounds_pairings_ids):
            reply = QtWidgets.QMessageBox.question(self, "Re-Prepare Round?",
                                                   f"Pairings for Round {self.current_round_index + 1} already exist. Re-generate them?\n"
                                                   "This is usually not needed unless player active status changed significantly.",
                                                   QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                                   QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                # Clear existing pairings for this round to regenerate
                self.tournament.rounds_pairings_ids = self.tournament.rounds_pairings_ids[:self.current_round_index]
                self.tournament.rounds_byes_ids = self.tournament.rounds_byes_ids[:self.current_round_index]
                self.history_message.emit(f"--- Re-preparing pairings for Round {self.current_round_index + 1} ---")
            else: 
                # Just display existing pairings
                display_round_num = self.current_round_index + 1
                pairings_ids = self.tournament.rounds_pairings_ids[self.current_round_index]
                bye_id = self.tournament.rounds_byes_ids[self.current_round_index]
                pairings = []
                for w_id, b_id in pairings_ids:
                    w = self.tournament.players.get(w_id); b = self.tournament.players.get(b_id)
                    if w and b: pairings.append((w,b))
            
                bye_player = self.tournament.players.get(bye_id) if bye_id else None
                self.lbl_round_title.setText(f"Round {display_round_num} Pairings & Results")
                self.display_pairings_for_input(pairings, bye_player)
                self.update_ui_state()
                return


        display_round_number = self.current_round_index + 1
        self.status_message.emit(f"Generating pairings for Round {display_round_number}...")
        QtWidgets.QApplication.processEvents()

        try:
            pairings, bye_player = self.tournament.create_pairings(
                display_round_number,
                allow_repeat_pairing_callback=self.prompt_repeat_pairing
            )
            
            if not pairings and len(self.tournament._get_active_players()) > 1 and not bye_player : # Handle cases where pairing might fail
                if len(self.tournament._get_active_players()) % 2 == 0 : # Even players, no bye expected, but no pairings
                     QtWidgets.QMessageBox.critical(self, "Pairing Error", f"Pairing generation failed for Round {display_round_number}. No pairings returned. Check logs and player statuses.")
                     self.status_message.emit(f"Error generating pairings for Round {display_round_number}.")
                     self.update_ui_state()
                     return
                # If odd players and no bye_player, also an issue if pairings are also empty.

            self.lbl_round_title.setText(f"Round {display_round_number} Pairings & Results")
            self.display_pairings_for_input(pairings, bye_player)
            self.history_message.emit(f"--- Round {display_round_number} Pairings Generated ---")
            for white, black in pairings: self.history_message.emit(f"  {white.name} (W) vs {black.name} (B)")
            if bye_player: self.history_message.emit(f"  Bye: {bye_player.name}")
            self.history_message.emit("-" * 20)
            self.dirty.emit()
            self.status_message.emit(f"Round {display_round_number} pairings ready. Enter results.")
        except Exception as e:
            logging.exception(f"Error generating pairings for Round {display_round_number}:")
            QtWidgets.QMessageBox.critical(self, "Pairing Error", f"Pairing generation failed for Round {display_round_number}:\n{e}")
            self.status_message.emit(f"Error generating pairings for Round {display_round_number}.")
        finally:
             self.update_ui_state()

    def prepare_next_round(self) -> None:
        if not self.tournament: return

        # round_to_prepare_idx is the index for rounds_pairings_ids (0 for R1, 1 for R2, etc.)
        # This should align with self.current_round_index if it means "next round to play/pair".
        # Or, more accurately, completed_rounds is the number of rounds whose results are IN.
        # If current_round_index points to the round WHOSE PAIRINGS ARE SHOWN, then current_round_index = completed_rounds.
        # For example, after R1 results recorded, current_round_index becomes 1. Completed rounds = 1.
        # Pairings for R2 (index 1) are then generated. So pairings_generated_for_rounds = 2.
        
        round_to_prepare_idx = self.current_round_index 
        
        if round_to_prepare_idx >= self.tournament.num_rounds:
             QtWidgets.QMessageBox.information(self,"Tournament End", "All tournament rounds have been generated and processed.")
             self.update_ui_state(); return
        
        # Check if pairings for this round_to_prepare_idx already exist
        # This happens if "Prepare Next Round" is clicked again without "Record Results"
        if round_to_prepare_idx < len(self.tournament.rounds_pairings_ids):
            reply = QtWidgets.QMessageBox.question(self, "Re-Prepare Round?",
                                                   f"Pairings for Round {round_to_prepare_idx + 1} already exist. Re-generate them?\n"
                                                   "This is usually not needed unless player active status changed significantly.",
                                                   QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                                   QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                # Clear existing pairings for this round to regenerate
                self.tournament.rounds_pairings_ids = self.tournament.rounds_pairings_ids[:round_to_prepare_idx]
                self.tournament.rounds_byes_ids = self.tournament.rounds_byes_ids[:round_to_prepare_idx]
                # We might need to clear previous_matches entries that were added for this specific round too.
                # This is complex. For now, re-pairing might result in same opponent if not careful.
                # A safer "re-prepare" might involve more state rollback.
                # Simpler: just let create_pairings run again. It checks previous_matches.
                self.history_message.emit(f"--- Re-preparing pairings for Round {round_to_prepare_idx + 1} ---")
            else: # User chose not to re-prepare
                # Just display existing pairings
                display_round_num = round_to_prepare_idx + 1
                pairings_ids = self.tournament.rounds_pairings_ids[round_to_prepare_idx]
                bye_id = self.tournament.rounds_byes_ids[round_to_prepare_idx]
                pairings = []
                for w_id, b_id in pairings_ids:
                    w = self.tournament.players.get(w_id); b = self.tournament.players.get(b_id)
                    if w and b: pairings.append((w,b))
            
                bye_player = self.tournament.players.get(bye_id) if bye_id else None
                self.lbl_round_title.setText(f"Round {display_round_num} Pairings & Results")
                self.display_pairings_for_input(pairings, bye_player)
                self.update_ui_state()
                return


        display_round_number = self.current_round_index + 1
        self.status_message.emit(f"Generating pairings for Round {display_round_number}...")
        QtWidgets.QApplication.processEvents()

        try:
            # create_pairings expects 1-based round number for its internal logic (e.g. R1 specific)
            pairings, bye_player = self.tournament.create_pairings(
                display_round_number,
                allow_repeat_pairing_callback=self.prompt_repeat_pairing
            )
            
            if not pairings and len(self.tournament._get_active_players()) > 1 and not bye_player : # Handle cases where pairing might fail
                if len(self.tournament._get_active_players()) % 2 == 0 : # Even players, no bye expected, but no pairings
                     QtWidgets.QMessageBox.critical(self, "Pairing Error", f"Pairing generation failed for Round {display_round_number}. No pairings returned. Check logs and player statuses.")
                     self.status_message.emit(f"Error generating pairings for Round {display_round_number}.")
                     self.update_ui_state()
                     return
                # If odd players and no bye_player, also an issue if pairings are also empty.

            self.lbl_round_title.setText(f"Round {display_round_number} Pairings & Results")
            self.display_pairings_for_input(pairings, bye_player)
            self.history_message.emit(f"--- Round {display_round_number} Pairings Generated ---")
            for white, black in pairings: self.history_message.emit(f"  {white.name} (W) vs {black.name} (B)")
            if bye_player: self.history_message.emit(f"  Bye: {bye_player.name}")
            self.history_message.emit("-" * 20)
            self.dirty.emit()
            self.status_message.emit(f"Round {display_round_number} pairings ready. Enter results.")
        except Exception as e:
            logging.exception(f"Error generating pairings for Round {display_round_number}:")
            QtWidgets.QMessageBox.critical(self, "Pairing Error", f"Pairing generation failed for Round {display_round_number}:\n{e}")
            self.status_message.emit(f"Error generating pairings for Round {display_round_number}.")
        finally:
             self.update_ui_state()

    def prompt_repeat_pairing(self, player1, player2):
        msg = (f"No valid new opponent found for {player1.name}.\n"
               f"Would you like to allow a repeat pairing with {player2.name} to ensure all players are paired?")
        reply = QtWidgets.QMessageBox.question(
            self,
            "Repeat Pairing Needed",
            msg,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes

    def display_pairings_for_input(self, pairings: List[Tuple[Player, Player]], bye_player: Optional[Player]):
        self.table_pairings.clearContents()
        self.table_pairings.setRowCount(len(pairings))

        current_round_display_idx = self.current_round_index # Round whose pairings are being shown
        # Disable adjust button if results for this round are already submitted (i.e., current_round_index has advanced past this one)
        # This check is slightly complex because display_pairings_for_input is called for current or past (undone) round.
        # Generally, if we are *inputting* results, current_round_index matches the displayed round's index.
        # So, can_adjust is true if round_index_of_pairings == self.current_round_index.
        # We need to know the actual index of the round these pairings belong to.
        # This function is called by prepare_next_round (for self.current_round_index)
        # and by undo_last_results (for self.current_round_index, which is the undone round)
        # So, adjustment is for the round currently indexed by self.current_round_index.
        can_adjust_pairings = True # Assume yes unless logic to disable is added for "already recorded" state.
                                  # Manual adjust should only be before results are recorded.

        for row, (white, black) in enumerate(pairings):
            item_white = QtWidgets.QTableWidgetItem(f"{white.name} ({white.rating})" + (" (I)" if not white.is_active else ""))
            item_white.setFlags(item_white.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_white.setToolTip(f"ID: {white.id}\nColor History: {' '.join(c or '_' for c in white.color_history)}")
            if not white.is_active: item_white.setForeground(QtGui.QColor("gray"))
            self.table_pairings.setItem(row, 0, item_white)

            item_black = QtWidgets.QTableWidgetItem(f"{black.name} ({black.rating})" + (" (I)" if not black.is_active else ""))
            item_black.setFlags(item_black.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_black.setToolTip(f"ID: {black.id}\nColor History: {' '.join(c or '_' for c in black.color_history)}")
            if not black.is_active: item_black.setForeground(QtGui.QColor("gray"))
            self.table_pairings.setItem(row, 1, item_black)

            # New ResultSelector widget
            result_selector = ResultSelector()
            result_selector.setProperty("row", row)
            result_selector.setProperty("white_id", white.id)
            result_selector.setProperty("black_id", black.id)

            # Auto-set result for inactive players
            if not white.is_active and not black.is_active:
                result_selector.setResult(RESULT_DRAW) # 0-0 or F-F
            elif not white.is_active:
                result_selector.setResult(RESULT_BLACK_WIN) # Black wins by forfeit
            elif not black.is_active:
                result_selector.setResult(RESULT_WHITE_WIN) # White wins by forfeit
            
            self.table_pairings.setCellWidget(row, 2, result_selector)

        if bye_player:
            status = " (Inactive)" if not bye_player.is_active else ""
            bye_score_info = BYE_SCORE if bye_player.is_active else 0.0 # Reflects score based on active status
            self.lbl_bye.setText(f"Bye: {bye_player.name} ({bye_player.rating}){status} - Receives {bye_score_info} point")
            self.lbl_bye.setVisible(True)
        else:
            self.lbl_bye.setText("Bye: None"); self.lbl_bye.setVisible(False)

        self.table_pairings.resizeColumnsToContents()
        self.table_pairings.resizeRowsToContents()

    def clear_pairings_display(self):
        """Clears the pairings table and bye player label."""
        self.table_pairings.setRowCount(0)
        self.lbl_bye.setText("Bye: None")
        if self.tournament:
            self.lbl_round_title.setText(f"Round {self.current_round_index + 1} - Not Started")
        else:
            self.lbl_round_title.setText("No Tournament Loaded")

    def show_pairing_context_menu(self, pos: QtCore.QPoint):
        item = self.table_pairings.itemAt(pos)
        if not item or not self.tournament:
            return

        row = item.row()
        result_selector = self.table_pairings.cellWidget(row, 2)
        if not isinstance(result_selector, ResultSelector):
            return

        white_id = result_selector.property("white_id")
        black_id = result_selector.property("black_id")

        menu = QtWidgets.QMenu(self)
        adjust_action = menu.addAction("Manually Adjust Pairing...")
        
        # Only allow adjustment for the current round before results are recorded
        can_adjust = self.current_round_index < len(self.tournament.rounds_pairings_ids)
        adjust_action.setEnabled(can_adjust)

        # Use exec() which returns the triggered action
        action = menu.exec(self.table_pairings.viewport().mapToGlobal(pos))

        if action == adjust_action:
            self.prompt_manual_adjust(white_id, black_id)

    def prompt_manual_adjust(self, white_id: str, black_id: str):
         if not self.tournament: return

         # Manual adjustment applies to the round currently displayed for input,
         # which is self.current_round_index.

         if self.current_round_index >= len(self.tournament.rounds_pairings_ids):
              QtWidgets.QMessageBox.warning(self, "Adjust Error", "Cannot adjust pairings for a round not yet fully generated in backend.")
              return
         # Also check if results for this round_idx_to_adjust have already been "committed" by advancing current_round_index
         # This check is tricky. 'current_round_index' is the round results are FOR.
         # If record_and_advance was called, current_round_index would have incremented.
         # For now, assume if adjust button is clickable, it's for the current "inputtable" round.

         player_to_adjust = self.tournament.players.get(white_id) 
         current_opponent = self.tournament.players.get(black_id)
         if not player_to_adjust or not current_opponent:
              QtWidgets.QMessageBox.critical(self, "Adjust Error", "Could not find players for this pairing.")
              return

         available_opponents = [p for p_id, p in self.tournament.players.items()
                                if p.is_active and p_id != white_id and p_id != black_id]
         
         # Also consider current bye player as a potential opponent IF a bye exists for this round.
         current_bye_id_for_round = self.tournament.rounds_byes_ids[self.current_round_index]
         if current_bye_id_for_round and current_bye_id_for_round not in [white_id, black_id]:
             bye_player_obj = self.tournament.players.get(current_bye_id_for_round)
             if bye_player_obj and bye_player_obj.is_active: # Can only pair with active bye player
                 # Check if already in list (should not be due to p_id != white_id etc.)
                 if not any(avail_p.id == bye_player_obj.id for avail_p in available_opponents):
                     available_opponents.append(bye_player_obj)


         dialog = ManualPairDialog(player_to_adjust.name, current_opponent.name, available_opponents, self)
         if dialog.exec():
              new_opponent_id = dialog.get_selected_opponent_id()
              if new_opponent_id:
                   new_opp_player = self.tournament.players.get(new_opponent_id)
                   if not new_opp_player: 
                       QtWidgets.QMessageBox.critical(self, "Adjust Error", "Selected new opponent not found.")
                       return

                   reply = QtWidgets.QMessageBox.warning(self, "Confirm Manual Pairing",
                                                       f"Manually pair {player_to_adjust.name} against {new_opp_player.name} for Round {self.current_round_index+1}?\n"
                                                       f"This will attempt to adjust other affected pairings.\n"
                                                       f"This action is logged. Undoing might require manual fixes if complex.",
                                                       QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                                       QtWidgets.QMessageBox.StandardButton.No)
                   if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                        if self.tournament.manually_adjust_pairing(self.current_round_index, white_id, new_opponent_id):
                             self.history_message.emit(f"MANUAL PAIRING: Round {self.current_round_index+1}, {player_to_adjust.name} vs {new_opp_player.name}. Other pairs adjusted.")
                             # Refresh the pairings display for the current round
                             current_pairings_ids = self.tournament.rounds_pairings_ids[self.current_round_index]
                             current_bye_id = self.tournament.rounds_byes_ids[self.current_round_index]
                             refreshed_pairings = []
                             for w_id, b_id in current_pairings_ids:
                                  w = self.tournament.players.get(w_id)
                                  b = self.tournament.players.get(b_id)
                                  if w and b: refreshed_pairings.append((w,b))
                             refreshed_bye_player = self.tournament.players.get(current_bye_id) if current_bye_id else None
                             self.display_pairings_for_input(refreshed_pairings, refreshed_bye_player)
                             self.dirty.emit()
                        else:
                             QtWidgets.QMessageBox.critical(self, "Adjust Error", "Manual pairing adjustment failed. Check logs. Pairings might be inconsistent.")

    def record_and_advance(self) -> None:
        if not self.tournament: return
        
        # Results are for the round currently displayed, which is self.current_round_index
        round_index_to_record = self.current_round_index
        
        if round_index_to_record >= len(self.tournament.rounds_pairings_ids):
             QtWidgets.QMessageBox.warning(self, "Record Error", "No pairings available to record results for this round index.")
             return

        results_data, all_entered = self.get_results_from_table()
        if not all_entered:
            QtWidgets.QMessageBox.warning(self, "Incomplete Results", "Please enter a result for all pairings.")
            return
        if results_data is None: 
             QtWidgets.QMessageBox.critical(self, "Input Error", "Error retrieving results from table. Cannot proceed.")
             return

        try:
            if self.tournament.record_results(round_index_to_record, results_data):
                self.last_recorded_results_data = list(results_data) # Store deep copy for undo
                
                display_round_number = round_index_to_record + 1
                self.history_message.emit(f"--- Round {display_round_number} Results Recorded ---")
                self.log_results_details(results_data, round_index_to_record)

                # Advance current_round_index *after* successful recording and logging
                self.current_round_index += 1
                # Notify main window of round advancement
                self.round_completed.emit(self.current_round_index)

                self.standings_update_requested.emit()
                
                if self.current_round_index >= self.tournament.num_rounds:
                    self.status_message.emit(f"Tournament finished after {self.tournament.num_rounds} rounds.")
                    self.history_message.emit(f"--- Tournament Finished ({self.tournament.num_rounds} Rounds) ---")
                    # Clear pairings table as no more rounds to input
                    self.table_pairings.setRowCount(0)
                    self.lbl_bye.setText("Bye: None")
                    self.lbl_round_title.setText("Tournament Finished")
                else:
                    self.status_message.emit(f"Round {display_round_number} results recorded. Prepare Round {self.current_round_index + 1}.")
                    # Clear pairings table for next round prep
                    self.table_pairings.setRowCount(0)
                    self.lbl_bye.setText("Bye: None")
                    self.lbl_round_title.setText(f"Round {self.current_round_index + 1} (Pending Preparation)")


                self.dirty.emit()
            else: # record_results returned False
                 QtWidgets.QMessageBox.warning(self, "Recording Warning", "Some results may not have been recorded properly by the backend. Check logs and player status.")

        except Exception as e:
            logging.exception(f"Error during record_and_advance for round {round_index_to_record+1}:")
            QtWidgets.QMessageBox.critical(self, "Recording Error", f"Recording results failed:\n{e}")
            self.status_message.emit("Error recording results.")
        finally:
             self.update_ui_state()

    def print_pairings(self):
        # Print the current round's pairings table in a clean, ink-friendly, professional format (no input widgets).
        from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        from PyQt6.QtGui import QTextDocument
        from PyQt6.QtCore import QDateTime
        if self.table_pairings.rowCount() == 0:
            QtWidgets.QMessageBox.information(self, "Print Pairings", "No pairings to print.")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Print Preview - Pairings")
        def render_preview(printer_obj):
            doc = QTextDocument()
            round_title = self.lbl_round_title.text() if hasattr(self, "lbl_round_title") else ""
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; color: #000; background: #fff; margin: 0; padding: 0; }}
                    h2 {{ text-align: center; margin: 0 0 0.5em 0; font-size: 1.35em; font-weight: normal; letter-spacing: 0.03em; }}
                    .subtitle {{ text-align: center; font-size: 1.05em; margin-bottom: 1.2em; }}
                    table.pairings {{ border-collapse: collapse; width: 100%; margin: 0 auto 1.5em auto; }}
                    table.pairings th, table.pairings td {{ border: 1px solid #222; padding: 6px 10px; text-align: left; font-size: 11pt; white-space: nowrap; }}
                    table.pairings th {{ font-weight: bold; background: none; }}
                    .bye-row td {{ font-style: italic; font-weight: bold; text-align: center; border-top: 2px solid #222; }}
                    .footer {{ text-align: center; font-size: 9pt; margin-top: 2em; color: #888; letter-spacing: 0.04em; }}
                </style>
            </head>
            <body>
                <h2>Pairings</h2>
                <div class="subtitle">{round_title}</div>
                <table class="pairings">
                    <tr>
                        <th style="width:7%;">Bd</th>
                        <th style="width:46%;">White</th>
                        <th style="width:46%;">Black</th>
                    </tr>
            """
            for row in range(self.table_pairings.rowCount()):
                white_item = self.table_pairings.item(row, 0)
                black_item = self.table_pairings.item(row, 1)
                html += f"<tr><td>{row+1}</td><td>{white_item.text() if white_item else ''}</td><td>{black_item.text() if black_item else ''}</td></tr>"
            if self.lbl_bye.isVisible() and self.lbl_bye.text() and self.lbl_bye.text() != "Bye: None":
                html += f'<tr class="bye-row"><td colspan="3">{self.lbl_bye.text()}</td></tr>'
            html += f"""
                </table>
                <div class="footer">
                    Printed by Gambit Pairing &mdash; {QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm')}
                </div>
            </body>
            </html>
            """
            doc.setHtml(html)
            doc.print(printer_obj)
        preview.paintRequested.connect(render_preview)
        preview.exec()

    def get_results_from_table(self) -> Tuple[Optional[List[Tuple[str, str, float]]], bool]:
         results_data = []
         all_entered = True
         if self.table_pairings.rowCount() == 0 and self.lbl_bye.text() == "Bye: None": # No pairings, no bye
             return [], True # Valid state of no results to record (e.g. if round had only a bye that was withdrawn)

         for row in range(self.table_pairings.rowCount()):
              result_selector = self.table_pairings.cellWidget(row, 2)
              if isinstance(result_selector, ResultSelector):
                  result_const = result_selector.selectedResult()
                  white_id = result_selector.property("white_id")
                  black_id = result_selector.property("black_id")

                  if not result_const:
                      all_entered = False
                      break 

                  white_score = -1.0
                  if result_const == RESULT_WHITE_WIN: white_score = WIN_SCORE
                  elif result_const == RESULT_DRAW: white_score = DRAW_SCORE
                  elif result_const == RESULT_BLACK_WIN: white_score = LOSS_SCORE
                  
                  if white_score >= 0 and white_id and black_id: 
                       results_data.append((white_id, black_id, white_score))
                  else: 
                       logging.error(f"Invalid result data in table row {row}: Result='{result_const}', W_ID='{white_id}', B_ID='{black_id}'")
                       if not white_id or not black_id: return None, False 
                       all_entered = False
                       break
              else: 
                  logging.error(f"Missing ResultSelector in pairings table, row {row}. Table improperly configured.")
                  return None, False
         return results_data, all_entered

    def log_results_details(self, results_data, round_index_recorded):
        bye_id = self.tournament.rounds_byes_ids[round_index_recorded]
         # Log paired game results
        for w_id, b_id, score_w in results_data:
              w = self.tournament.players.get(w_id) # Assume player exists
              b = self.tournament.players.get(b_id)
              score_b_display = f"{WIN_SCORE - score_w:.1f}" # Calculate display for black's score
              self.history_message.emit(f"  {w.name if w else w_id} ({score_w:.1f}) - {b.name if b else b_id} ({score_b_display})")
         
         # Log bye if one was assigned for the undone round
        if round_index_recorded < len(self.tournament.rounds_byes_ids):
            bye_id = self.tournament.rounds_byes_ids[round_index_recorded]
            if bye_id:
                bye_player = self.tournament.players.get(bye_id)
                if bye_player:
                    status = " (Inactive - No Score)" if not bye_player.is_active else ""
                    # Actual score for bye is handled by record_results based on active status
                    bye_score_awarded = BYE_SCORE if bye_player.is_active else 0.0
                    self.history_message.emit(f"  Bye point ({bye_score_awarded:.1f}) awarded to: {bye_player.name}{status}")
                else:
                    self.history_message.emit(f"  Bye player ID {bye_id} not found in player list (error).")
        self.history_message.emit("-" * 20)

    def undo_last_results(self) -> None:
        if not self.tournament or not self.last_recorded_results_data or self.current_round_index == 0:
            # current_round_index is index of NEXT round to play. If 0, no rounds completed.
            QtWidgets.QMessageBox.warning(self, "Undo Error", "No results from a completed round are available to undo."); return

        round_to_undo_display_num = self.current_round_index # e.g. if current_round_index is 1, we undo R1 results.
        
        reply = QtWidgets.QMessageBox.question(self,"Undo Results", 
                                             f"Undo results from Round {round_to_undo_display_num} and revert to its pairing stage?",
                                             QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                             QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes: return

        try:
            # The round whose results are being undone (0-indexed)
            round_index_being_undone = self.current_round_index - 1
            
            # Revert player stats for each game in last_recorded_results_data
            for white_id, black_id, _ in self.last_recorded_results_data:
                p_white = self.tournament.players.get(white_id)
                p_black = self.tournament.players.get(black_id)
                if p_white: self._revert_player_round_data(p_white)
                if p_black: self._revert_player_round_data(p_black)
            
            # Revert bye player stats if a bye was given in the undone round
            if round_index_being_undone < len(self.tournament.rounds_byes_ids):
                bye_player_id_undone_round = self.tournament.rounds_byes_ids[round_index_being_undone]
                if bye_player_id_undone_round:
                    p_bye = self.tournament.players.get(bye_player_id_undone_round)
                    if p_bye: self._revert_player_round_data(p_bye)

            # Crucial: Do NOT pop from tournament's rounds_pairings_ids or rounds_byes_ids here.
            # These store the historical pairings. Undoing results means we are going back to the
            # state *before* these results were entered for that specific round's pairings.
            # The pairings themselves remain.
            
            # If manual pairings were made for the round being undone, they are part of its history.
            # They are not automatically "undone" unless the user manually re-pairs.
            if round_index_being_undone in self.tournament.manual_pairings:
                 logging.warning(f"Manual pairings for round {round_to_undo_display_num} were part of its setup and are not automatically reverted by undoing results.")

            self.last_recorded_results_data = [] # Clear the stored results for "can_undo" check
            self.current_round_index -= 1 # Decrement GUI's round counter

            # --- Update UI ---
            # Re-display pairings for the round being "re-opened" for input
            self.lbl_round_title.setText(f"Round {self.current_round_index + 1} Pairings & Results (Re-entry)")
            
            pairings_ids_to_redisplay = self.tournament.rounds_pairings_ids[self.current_round_index]
            bye_id_to_redisplay = self.tournament.rounds_byes_ids[self.current_round_index]
            
            pairings_to_redisplay = []
            for w_id, b_id in pairings_ids_to_redisplay:
                 w = self.tournament.players.get(w_id)
                 b = self.tournament.players.get(b_id)
                 if w and b: pairings_to_redisplay.append((w,b))
                 else: logging.warning(f"Load: Missing player for pairing ({w_id} vs {b_id}) in loaded round {self.current_round_index + 1}")
            
            bye_player_to_redisplay = self.tournament.players.get(bye_id_to_redisplay) if bye_id_to_redisplay else None
            
            self.display_pairings_for_input(pairings_to_redisplay, bye_player_to_redisplay)
            self.tabs.setCurrentWidget(self.tournament_tab)

            self.standings_update_requested.emit() # Reflect reverted scores
            self.history_message.emit(f"--- Round {round_to_undo_display_num} Results Undone ---")
            self.status_message.emit(f"Round {round_to_undo_display_num} results undone. Re-enter results or re-prepare round.")
            self.dirty.emit()

        except Exception as e:
            logging.exception(f"Error undoing results:")
            QtWidgets.QMessageBox.critical(self, "Undo Error", f"Undoing results failed:\n{e}")
            self.status_message.emit("Error undoing results.")
        finally:
             self.update_ui_state()

    def _revert_player_round_data(self, player: Player):
         """Helper to remove the last round's data from a player object's history lists."""
         if not player.results: return # No results to revert
         
         last_result = player.results.pop()
         # Score is recalculated from scratch or by subtracting. Subtracting is simpler here.
         if last_result is not None: player.score = round(player.score - last_result, 1) # round to handle float issues

         if player.running_scores: player.running_scores.pop()
         
         last_opponent_id = player.opponent_ids.pop() if player.opponent_ids else None
         last_color = player.color_history.pop() if player.color_history else None
         
         if last_color == "Black": player.num_black_games = max(0, player.num_black_games -  1)
         
         if last_opponent_id is None: # Means the undone round was a bye for this player
             # Check if they *still* have other byes in their history.
             # If not, has_received_bye becomes False.
             player.has_received_bye = (None in player.opponent_ids) if player.opponent_ids else False
             logging.debug(f"Player {player.name} bye undone. Has received bye: {player.has_received_bye}")

         # Invalidate opponent cache, it will be rebuilt on next access
         player._opponents_played_cache = []

    def update_ui_state(self):
        tournament_exists = self.tournament is not None
        pairings_generated = len(self.tournament.rounds_pairings_ids) if tournament_exists else 0
        results_recorded = self.current_round_index if hasattr(self, 'current_round_index') else 0
        total_rounds = self.tournament.num_rounds if tournament_exists else 0
        tournament_started = tournament_exists and pairings_generated > 0

        print(f"[DEBUG] update_ui_state: tournament_exists={tournament_exists}, pairings_generated={pairings_generated}, results_recorded={results_recorded}, total_rounds={total_rounds}, tournament_started={tournament_started}")
        print(f"[DEBUG] self.tournament={self.tournament}")
        if tournament_exists:
            print(f"[DEBUG] self.tournament.rounds_pairings_ids={self.tournament.rounds_pairings_ids}")

        can_start = tournament_exists and not tournament_started
        can_prepare = tournament_exists and tournament_started and pairings_generated == results_recorded and pairings_generated < total_rounds
        can_record = tournament_exists and tournament_started and pairings_generated > results_recorded
        can_undo = tournament_exists and results_recorded > 0

        print(f"[DEBUG] can_start={can_start}, can_prepare={can_prepare}, can_record={can_record}, can_undo={can_undo}")

        # Removed button enables since buttons no longer exist in the tab
        # self.btn_start.setEnabled(can_start)
        # self.btn_next.setEnabled(can_prepare)
        # self.btn_record.setEnabled(can_record)
        # self.btn_undo.setEnabled(can_undo)

        # Optionally, disable the whole tab if no tournament
        self.setEnabled(tournament_exists)