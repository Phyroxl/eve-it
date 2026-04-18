@echo off
echo ==========================================
echo EVE iT - Script de Limpieza de Seguridad
echo ==========================================
echo.
echo Este script eliminara archivos temporales y redundantes.
echo Solo se mantendran los archivos esenciales del nucleo.
echo.
pause

del _apply.py _assemble.py _chk.py _chkline.py _co.txt _co_hdr.txt _colorfx.py _commit_cw.py _commit_overlay.py _countdown_new.py _cw_chars.txt _cw_full.txt _cwsec.txt _dbg.txt _dbg2.txt _deploy.py _fix.py _fix_local.py _fix_ui.py _force_commit.py _full.txt _gs.txt _gs2.txt _inspect.py _inspect2.py _lang_fix.py _lang_overlay.py _main_char_patch.py _main_patch_final.py _main_patch_v3.py _metric_new.py _mp.txt _overlay_new.py _push_gh.py _read.txt _read2.txt _resize_fix.py _restore.py _restore_check.py _retrans.py _revert_cw.py _rmbtn.py _rmsub.py _scale_btn.py _scale_p1.py _scale_p2.py _scale_p3.py _tmp.txt _tr.txt _ui_fix2.py
del test_chat.py test_tick.py tmp.py type CONTEXTO.md GENERAR_FLAGS.py GENERAR_PATCH.py generate_flags.py

echo.
echo Limpieza completada con exito.
echo.
pause
