##Setup:

Populate the "RAW" folder with csv files from Chase + Discover Accounts.

##To Run in Docker:
Copy and paste the commands below:
"
docker build -t personal-finance-app .
docker run -p 8050:8050 personal-finance-app
"

##To not run in docker:
"
source .venv/bin/activate                                                
 python app.py
"


##To exit:
If you're in a terminal that's running the Dash app,
you need to stop the app first with Ctrl+C, then run deactivate.
