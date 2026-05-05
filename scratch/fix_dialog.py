path = 'overlay/replicator_settings_dialog.py'
lines = open(path, 'r', encoding='utf-8').readlines()
new_lines = []
for line in lines:
    if 'btn_apply_hk = QPushButton(" Aplicar Hotkeys' in line:
        break
    new_lines.append(line)

new_lines.append('        btn_apply_hk = QPushButton("Aplicar Hotkeys")\n')
new_lines.append('        btn_apply_hk.setObjectName("blue")\n')
new_lines.append('        btn_apply_hk.clicked.connect(_save_all_hk)\n')
new_lines.append('        lay.addWidget(btn_apply_hk)\n')
new_lines.append('        lay.addWidget(lbl_hk_status)\n\n')
new_lines.append('        lay.addStretch()\n')
new_lines.append('        return w\n')

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
