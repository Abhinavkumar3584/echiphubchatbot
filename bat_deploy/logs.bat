@echo off
rem Shows the bot's live log on the server (Ctrl+C to stop)
ssh -i "%USERPROFILE%\.ssh\wordpress-test.pem" ubuntu@13.235.238.82 "sudo systemctl status chatbot --no-pager -l | head -n 5; sudo journalctl -u chatbot -n 40 -f"
