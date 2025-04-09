from flask import Flask, redirect, request, render_template, url_for, session, make_response, jsonify, flash
from flask_s3 import FlaskS3, create_all
import argparse
from datetime import datetime
from pytz import timezone
from functools import wraps
import time
import boto3
from botocore.exceptions import ClientError
from flask_cognito_auth import CognitoAuthManager, login_handler, logout_handler, callback_handler
import os
from typing import Dict
import json
from flask_cors import CORS

app = Flask(__name__)
cors = CORS(app)

from integrations.scishield.scishield_routes import scishield_bp
app.register_blueprint(scishield_bp, url_prefix='/chem-snap')
from integrations.scishield.scishield_routes2 import scishield_bp2
app.register_blueprint(scishield_bp2, url_prefix='/chemical_classification')

# Basic test endpoint
@app.route("/", methods=["GET"])
def test_endpoint():
    return '''API Chemical Proscessing - Online - 
    
    extention1- chem-snap/docs  
    
    extention2- chemical_classification/docs '''


if __name__ == "__main__":
    app.run()#host="0.0.0.0", port=5000)