""" Night Out """

from jinja2 import StrictUndefined
from flask_debugtoolbar import DebugToolbarExtension
from flask import (Flask, render_template, redirect, request, flash,
                   session, jsonify)
from model import *
import datetime
import requests
from urllib import urlencode, quote
import os
import bcrypt
import json
import sendgrid
from sendgrid.helpers.mail import *


app = Flask(__name__)

# Required to use Flask sessions and the debug toolbar
app.secret_key = "ABC"

# Normally, if you use an undefined variable in Jinja2, it fails
# silently. This is horrible. Fix this so that, instead, it raises an
# error.
app.jinja_env.undefined = StrictUndefined


def get_yelp_bearer_token():
    """ Get and cache yelp token id """

    # OS environ for client ID would not be accepted on Yelp side
    data = urlencode({
    'client_id': 's50ybEKVTcgO0rhu7bXKHA',
    'client_secret': os.environ['YELP_CLIENT_SECRET'],
    'grant_type': 'client_credentials',
    })

    headers = {'content-type': 'application/x-www-form-urlencoded'}
    host = 'https://api.yelp.com'
    path = '/oauth2/token'
    url = '{0}{1}'.format(host, quote(path.encode('utf8')))
    response = requests.request("POST", url, data=data, headers=headers)
    bearer_token = response.json()['access_token']
    return bearer_token


def send_email(plan_id, invitee_email, invitee_first_name, invitee_last_name):
    """ Send email to invited guests """
    sg = sendgrid.SendGridAPIClient(apikey=os.environ['SENDGRID_API_KEY'])

    plan = Plan.query.get(plan_id)
    

    # Set up email settings
    from_email = Email("donotreply@nightout.com", "Night Out Concierge")
    subject = "Plan for " + plan.event_name + " on " + plan.event_time.strftime('%x')
    to_email = Email(invitee_email, invitee_first_name + " " + invitee_last_name)

    # HTML to represent body of email
    html_header="<h3>"+plan.event_time.strftime('%x') + " " + plan.plan_name+ "</h3>"
    html_event = "<h4>" + plan.event_time.strftime('%-I:%M %p')+ ": " + plan.event_name + "</h4>"
    
    html_evlocation = ""
    if plan.event_location:
        html_evlocation = "<p>"+ plan.event_location + "</p>"
    html_evaddress = "<p>" + plan.event_address + "</p><p>" + plan.event_city+ ", " + plan.event_state+ " " + plan.event_zipcode

    html_food = ""
    if (plan.food_name) and (plan.food_time):
        html_food = "<h4>" + plan.food_time.strftime('%-I:%M %p')+": "+plan.food_name+"</h4><p>"+plan.food_address+"</p><p>"+plan.food_city+", "+plan.food_state+" "+plan.food_zipcode+"</p>"

    html_string = html_header+html_food+html_event+html_evlocation+html_evaddress

    content = Content("text/html", "<html><body>" + html_string + "</body></html>")

    mail = Mail(from_email, subject, to_email, content)

    # Send e-mail and get status message
    data = mail.get()
    response = sg.client.mail.send.post(request_body=data)
    print(response.status_code)
    print(response.body)
    print(response.headers)

    


@app.route('/')
def index():
    """Homepage."""
    return render_template("homepage.html")


@app.route('/create-account')
def create_account():
    """ Allows user to create a new account """
    return render_template('create_account.html')

@app.route('/create-account', methods=['POST'])
def create_new_user():
    """ Checks user email is new and processes registration 

    Adds plans that user was previously an invitee
    """
    
    # Extract all data from account creation form
    user_email = request.form.get('email')
    user_password = request.form.get('password')
    user_first_name = request.form.get('first_name')
    user_last_name = request.form.get('last_name')
    user_zip = request.form.get('zip_code')

    # Encode password
    hashed = bcrypt.hashpw(user_password.encode('utf8'), bcrypt.gensalt(9))

    user = User.query.filter_by(email=user_email).all()

    # User email already used for a user
    if user:
        flash("User email already exists")
        return redirect('/login-form')
    # Create new user and log in
    else:
        new_user = User(email=user_email, password=hashed, 
                        first_name=user_first_name, last_name=user_last_name, 
                        zipcode=user_zip)

        # Add new user to the databased
        db.session.add(new_user)

        # Flush db to get new_user user_id
        db.session.flush()

        # Check if user has had previous invites and add them to userplans
        previously_invited = Invitee.query.filter_by(email=user_email).all()

        db.session.commit()
        # Loop through all previous invites and add user plans to associate to user
        if previously_invited:
            for previous_plan in previously_invited:
                new_user_plan = UserPlan(plan_id=previous_plan.plan_id, user_id=new_user.user_id)
                db.session.add(new_user_plan)
                db.session.commit()


        session['current_user'] = user_email
        flash('You are now registered and logged in!')

        return redirect('/profile')

@app.route('/logout')
def logout():
    """Logs out user"""
    del session['current_user']
    flash("You are now logged out.")
    return redirect('/login-form')

@app.route('/login-form')
def login():
    """Prompts user to log in"""
    return render_template('login_form.html')


@app.route('/check-login', methods=['POST'])
def check_login():
    """Check if email in users table"""

    # Extract data from form
    user_email = request.form.get('email')
    user_password = request.form.get('password')

    # Look for user in database and match password
    try:
        user = User.query.filter_by(email=user_email).one()
        if bcrypt.checkpw(user_password.encode('utf8'), user.password.encode('utf8')):
            session['current_user'] = user_email
            flash('You are now logged in!')
            return redirect('/profile')
        else:
            flash('Wrong password!')
            return redirect('/login-form')

    # If user does not exist, re-direct to account creation
    except:
        flash("No user with that email")
        return redirect('/create-account')


@app.route('/profile')
def user_profile():
    """ Dashboard for all user's plans """

    # Query database for all plans for a logged-in user
    current_user = User.query.filter_by(email=session['current_user']).first()
    plans = current_user.plans
    current_user_id = current_user.user_id

    return render_template('all_plans.html', plans=plans, current_user=current_user_id)


@app.route('/new-plan')
def new_plan():
    """ User creates a new plan """
    if not session['current_user']:
        return redirect('/login-form')
    else:
        return render_template('add_plan.html')

@app.route('/new-plan', methods=['POST'])
def add_new_plan():
    """ Adds event to user's new plan """

    # Extract data from plan form
    new_plan_name = request.form.get('plan_name')
    new_event_name = request.form.get('event_name')
    new_plan_date = request.form.get('event_date')
    new_plan_time = request.form.get('event_time')
    new_event_datetime = datetime.datetime.strptime(new_plan_date + " " + new_plan_time, "%Y-%m-%d %H:%M")
    new_plan_location = request.form.get('location')
    new_plan_number = request.form.get('number')
    new_plan_street = request.form.get('street')
    new_plan_state = request.form.get('state')
    new_plan_city = request.form.get('city')
    new_plan_zipcode = request.form.get('zipcode')

    new_plan_address = new_plan_number + " " + new_plan_street
    # If user chooses to not name plan right away - defaults to the event name
    if new_plan_name == "":
        new_plan_name = new_event_name

    current_user_id = User.query.filter_by(email=session['current_user']).first().user_id

    # Create new plan object with plan attributes
    new_plan = Plan(plan_user_creator=current_user_id, plan_name=new_plan_name, 
                    event_name=new_event_name, event_time=new_event_datetime, 
                    event_location=new_plan_location, event_address=new_plan_address, 
                    event_state=new_plan_state, event_city=new_plan_city, 
                    event_zipcode=new_plan_zipcode)
    
    # Add plan to Plan database
    db.session.add(new_plan)
    db.session.flush()
    current_plan_id = new_plan.plan_id
    db.session.commit()

    # Add association between User and Plan in UserPlan database
    new_userplan = UserPlan(user_id=current_user_id, plan_id=current_plan_id)
    db.session.add(new_userplan)
    db.session.commit()

    # Choose a restaurant
    return redirect('/choose-restaurant/'+str(current_plan_id))

@app.route('/edit-plan/<plan_id>')
def edit_plan(plan_id):
    """ User edits an existing plan they own """
    
    # Pull current user from session and plan id from route
    current_user = User.query.filter_by(email=session['current_user']).first().user_id
    plan = Plan.query.get(plan_id)

    # Check plan_id exists and that current user is the creator
    if not plan:
        flash("Plan does not exist")
        return redirect('/profile')

    elif current_user != plan.plan_user_creator:
        flash("Only plan creator may edit plan")
        return redirect('/profile')   

    else:

        # Separate date and time from datetime object in database
        plan_datetime = plan.event_time
        plan_date = plan_datetime.date()
        plan_date = plan_date.strftime("%Y-%m-%d")
        plan_time = plan_datetime.time()
        plan_time = plan_time.strftime("%H:%M")

        return render_template('edit_plan.html', plan=plan, plan_date=plan_date, plan_time=plan_time)


@app.route('/edit-plan/<plan_id>', methods=['POST'])
def edit_event_plan(plan_id):
    """ Adds event to user's new plan """
    plan = Plan.query.get(plan_id)

    # Extract data from plan form
    new_plan_name = request.form.get('plan_name')
    new_event_name = request.form.get('event_name')
    new_plan_date = request.form.get('event_date')
    new_plan_time = request.form.get('event_time')
    new_event_datetime = datetime.datetime.strptime(new_plan_date + " " + new_plan_time, "%Y-%m-%d %H:%M")
    new_plan_location = request.form.get('location')
    new_plan_number = request.form.get('number')
    new_plan_street = request.form.get('street')
    new_plan_state = request.form.get('state')
    new_plan_city = request.form.get('city')
    new_plan_zipcode = request.form.get('zipcode')

    # Mark if event's location has changed to allow user to choose a different restaurant
    if new_plan_location != plan.event_location:
        different_location = True
    else:
        different_location = False

    new_plan_address = new_plan_number + " " + new_plan_street

    # If user chooses to not name plan right away - defaults to the event name
    if new_plan_name == "":
        new_plan_name = new_event_name

    current_user_id = User.query.filter_by(email=session['current_user']).first().user_id

    # Edit plan object with plan attributes
    plan.plan_name = new_plan_name
    plan.event_name = new_event_name
    plan.event_time = new_event_datetime
    plan.event_location = new_plan_location
    plan.event_address = new_plan_address
    plan.event_state = new_plan_state
    plan.event_city = new_plan_city
    plan.event_zipcode = new_plan_zipcode

    db.session.commit()

    if different_location == False:
        return redirect('/profile')
    else:
        return redirect('/choose-restaurant/'+str(plan.plan_id))


@app.route('/yelp.json', methods=["POST"])
def choose_restaurant():
    """ Allows a user to choose a restaurant to add to plan """

    # Get user preferences from first "customize" form
    plan_id = int(request.form.get("plan_id"))
    business = str(request.form.get("bar_or_rest"))
    time_before = float(request.form.get("time_before"))
    distance = float(request.form.get("distance"))

    current_plan = Plan.query.get(plan_id)

    # Calculate time to meet at restaurant/ bar and save it to plan
    food_time = current_plan.event_time - datetime.timedelta(hours=time_before)
    current_plan.food_time = food_time
    db.session.commit()

    # Calculating parameters for Yelp API call
    location = current_plan.event_address+" "+current_plan.event_city+" "+current_plan.event_state+ " "+current_plan.event_zipcode
    radius = int(distance * 1600)
    unix_time = int((food_time - datetime.datetime(1970, 1, 1)).total_seconds())

    headers = {
        'Authorization': 'Bearer %s' % app.yelp_bearer_token,
    }

    rest_url_params = {
        'term': business,
        'location': location.replace(' ', '+'),
        'limit': 20,
        'radius': radius,
    }

    r = requests.request('GET', 'https://api.yelp.com/v3/businesses/search', headers=headers, params=rest_url_params)
    response = r.json()

    return jsonify(response['businesses'])


@app.route('/choose-restaurant/<plan_id>')
def customize_restaurant(plan_id):
    """ Allows a user to customize distance from location, time meeting and whether a restaurant or bar """
    return render_template("customize_business.html", current_plan_id=plan_id)


@app.route('/choose-restaurant/<plan_id>', methods=['POST'])
def add_plan_restaurant(plan_id):
    """ Adds restaurant or bar to user's current plan """
    headers = {
        'Authorization': 'Bearer %s' % app.yelp_bearer_token,
    }

    try: 
        chosen_id = request.form.get('event_food')
        food_chosen = json.loads(chosen_id)


        # Get current plan and update with yelp listing details
        current_plan = Plan.query.get(plan_id)

        current_plan.food_name = food_chosen['name']
        current_plan.food_address = food_chosen['location']['address1']
        current_plan.food_city = food_chosen['location']['city']
        current_plan.food_state = food_chosen['location']['state']
        current_plan.food_zipcode = food_chosen['location']['zip_code']
        current_plan.food_longitude = food_chosen['coordinates']['longitude']
        current_plan.food_latitude = food_chosen['coordinates']['latitude']

        db.session.commit()

        return redirect('/add-friends/'+str(plan_id))

    except:
        flash("Something went wrong. Please try again later.")
        return redirect('/profile')


@app.route('/add-friends/<plan_id>')
def add_friends(plan_id):
    """ Add users friends to plan """
    plan = Plan.query.get(plan_id)

    # If user got re-directed here through editing restaurant, take back to profile
    if plan.invitees:
        return redirect('/profile')

    else:
        return render_template("add_friends.html", plan=plan)


@app.route('/add-more-friends/<plan_id>')
def add_more_friends(plan_id):
    """ Add more users friends to plan through 'add friends' button """
    plan = Plan.query.get(plan_id)

    return render_template("add_friends.html", plan=plan)

@app.route('/add-friends/<plan_id>', methods=['POST'])
def add_invitees(plan_id):
    """ Add users friends to plan """
    current_user_id = User.query.filter_by(email=session['current_user']).first().user_id

    # Check if user inputted any friends
    added_friends = False

    for friend in range(12):
        if request.form.get('fname'+str(friend)):
            added_friends = True
            fname = request.form.get('fname'+str(friend))
            lname = request.form.get('lname'+str(friend))
            email = request.form.get('email'+str(friend))
            phone = request.form.get('phone'+str(friend))
            new_invitee = Invitee(plan_id=plan_id, user_id=current_user_id, 
                                first_name=fname, last_name=lname, email=email,
                                phone=phone)
            db.session.add(new_invitee)

            # E-mail user notifying of being added to plan
            send_email(plan_id=plan_id, invitee_email=email, invitee_first_name=fname, invitee_last_name=lname)

            # Check if invitee has an account and add plan to their userplan
            invitee_user = User.query.filter_by(email=email).first()

            if invitee_user:
                new_user_plan = UserPlan(plan_id=plan_id, user_id=invitee_user.user_id)
                db.session.add(new_user_plan)
            
            db.session.commit()


    return redirect ('/profile')


if __name__ == "__main__":
    # We have to set debug=True here, since it has to be True at the
    # point that we invoke the DebugToolbarExtension
    app.debug = True
    app.jinja_env.auto_reload = app.debug  # make sure templates, etc. are not cached in debug mode

    connect_to_db(app)

    app.yelp_bearer_token = 'WllJxLDGOspRQnGbwsoqd9CFqeW8_LshxaRo1WZXWbTJ5-zCePPbNwW61x1NCJiX9-RIh7KMiP-3l7RxJtrqnczHAILypbXeduWluvi3zK0OTUorLHk_9E3TbIMTWXYx'


    # Use the DebugToolbar
    # DebugToolbarExtension(app)
    app.run(port=5000, host='0.0.0.0')