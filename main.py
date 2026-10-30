from flask import Flask,request,redirect,url_for,render_template,flash,session,send_file
from mysql.connector import connect,Error
import bcrypt
from datetime import datetime,timedelta
from email.message import EmailMessage
import smtplib
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv
import os
import random
from functools import wraps
from werkzeug.utils import secure_filename
import re
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"]=os.getenv("SECRET_KEY")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt', 'doc', 'docx', 'png', 'jpg', 'jpeg'}

serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
salt = os.getenv('SALT_KEY')

DB_CONFIG = {
    "host":os.getenv("DB_HOST"), # localhost ip = 127.0.0.1
    "port":os.getenv("DB_PORT"),
    "user":os.getenv("DB_USER"),
    "password":os.getenv("DB_PASSWORD"),
    "database":os.getenv("DB_NAME"),
    "ssl_disabled": False
}

EMAIL_CONFIG = {
    'smtp_server' : 'smtp.gmail.com',
    'smtp_port' : 587,
    'email' : os.getenv("SMTP_EMAIL"),
    'password' : os.getenv("SMTP_PASSWORD")
}


# ==================== DATABASE INITIALIZATION ====================

def check_database_exists():
    """Check if database exists, create if not"""
    try:
        conn = connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cursor = conn.cursor()
        
        # Create database if not exists
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        print(f"✓ Database '{DB_CONFIG['database']}' is ready.")
        
        cursor.close()
        conn.close()
        return True
        
    except Error as err:
        if err.errno == 1045:  # Access denied
            print(f"✗ Database Error: Access denied. Check username/password in DB_CONFIG.")
        elif err.errno == 2003:  # Can't connect
            print(f"✗ Database Error: Cannot connect to MySQL server. Is MySQL running?")
        else:
            print(f"✗ Database Error: {err}")
        return False


def check_tables_exist():
    """Check if tables exist, create if not"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password VARCHAR(256) NOT NULL,
                otp VARCHAR(6) DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')
        print("✓ Table 'users' is ready.")
        
        # Create notes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Table 'notes' is ready.")
        
        # Create files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                note_id INT DEFAULT NULL,
                filename VARCHAR(255) NOT NULL,
                filepath VARCHAR(500) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE SET NULL
            )
        ''')
        print("✓ Table 'files' is ready.")
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
        
    except Error as err:
        print(f"✗ Table Creation Error: {err}")
        return False


def init_database():
    """Initialize database and create tables with proper error handling"""
    print("\n" + "="*50)
    print("SNM - Database Initialization")
    print("="*50)
    
    # Step 1: Check/Create Database
    print("\n[1/3] Checking database...")
    if not check_database_exists():
        print("\n⚠ Database initialization failed!")
        print("Please ensure MySQL is running and credentials are correct.")
        return False
    
    # Step 2: Check/Create Tables
    print("\n[2/3] Checking tables...")
    if not check_tables_exist():
        print("\n⚠ Table initialization failed!")
        return False
    
    # Step 3: Create upload folder
    print("\n[3/3] Checking upload folder...")
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        print(f"✓ Upload folder '{app.config['UPLOAD_FOLDER']}' is ready.")
    except OSError as err:
        print(f"✗ Upload Folder Error: {err}")
        return False
    
    print("\n" + "="*50)
    print("✓ Database initialization completed successfully!")
    print("="*50 + "\n")
    return True


def get_db_connection():
    """Create and return database connection with error handling"""
    try:
        conn = connect(**DB_CONFIG)
        return conn
    except Error as err:
        if err.errno == 1049:  # Unknown database
            print(f"Database '{DB_CONFIG['database']}' does not exist. Creating...")
            if check_database_exists() and check_tables_exist():
                return connect(**DB_CONFIG)
        raise err


# ==================== DATABASE CONNECTION DECORATOR ====================

def db_connection_required(f):
    """Decorator to handle database connection errors gracefully"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Error as err:
            if err.errno == 1049:  # Unknown database
                flash('Database not found. Please restart the application.', 'error')
            elif err.errno == 1146:  # Table doesn't exist
                flash('Database tables not found. Please restart the application.', 'error')
            elif err.errno == 2003:  # Can't connect
                flash('Cannot connect to database. Please check if MySQL is running.', 'error')
            else:
                flash(f'Database error: {err}', 'error')
            return redirect(url_for('home'))
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.split('.',1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


#Otp helper method
def generate_otp():
    # generate 6 digit otp
    return str(random.randint(100000,999999))

def send_email(to_email,subject,body,html=False):
    try:
        msg = EmailMessage()
        msg['subject'] = subject
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = to_email

        if html:
            msg.add_alternative(body,subtype='html')
        else:
            msg.set_content(body)

        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'],EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['email'],EMAIL_CONFIG['password'])
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Email error:{e}")
        return False

def generate_reset_token(email):
    return serializer.dumps(email,salt=salt)

def verify_reset_token(token,expiration=600):
    try:
        email = serializer.loads(token,salt=salt,max_age=expiration)
        return email
    except Exception as e:
        print(f"Token verification failed :{e}")
        return None


def login_required(f):
    @wraps(f)
    def decorated_function(*args,**kwargs):
        if not 'user_id' in session:
            flash("Please login to access this page.",'warning')
            return redirect(url_for('login'))
        return f(*args,**kwargs)
    return decorated_function



@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    return render_template('home.html')

# Let's define register router
@app.route('/register',methods=['POST','GET'])
def register():

    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method=='POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not name or not email or not password or not confirm_password:
            flash("All fields required!")
            return redirect(url_for('register'))

        if len(password)<6:
            flash("Password length must be greater 6-Characters...!")
            return redirect(url_for('register'))

        if password!=confirm_password:
            flash("Password and Confirm Password Do not match.")
            return redirect(url_for('register'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT email from users where email=%s",(email,))
            db_email = cursor.fetchone()

            # Check if email exists
            if db_email:
                flash("Email already exist! Please use login...!",'warning')
                cursor.close()
                conn.close()
                return redirect(url_for('register'))
            else:
                # Hash password with bcrypt
                hashed_pw = bcrypt.hashpw(password.encode('utf-8'),bcrypt.gensalt())

                otp = generate_otp()

                
                # Insert user
                cursor.execute("INSERT INTO users(name,email,password,otp) VALUES (%s,%s,%s,%s)",(name,email,hashed_pw,otp))
                conn.commit()

                session['pending_email'] = email

                # Send OTP Email
                email_body = f"""
                <h2>Welcome to SNM!</h2>
                <p>Your OTP for account verification is:</p>
                <h1 style="color: #667eea;">{otp}</h1>
                <p>This OTP will expire in 10 minutes.</p>
                """
                subject = 'SNM - Verify your Email'
                send_email(to_email=email,subject=subject,body=email_body,html=True)


                cursor.close()
                conn.close()
                flash("User registration Successful...! Please Verify your email...!",'success')
                return redirect(url_for('verify_otp'))

        except Error as err:
            flash(f"Database Error:{err}",'error')
            return redirect(url_for('register'))
        
    return render_template("register.html")

@app.route('/verify-otp',methods = ['GET','POST'])
def verify_otp():
    if 'pending_email' not in session:
        return redirect(url_for('register'))

    if request.method=='POST':
        otp = request.form.get('otp')
        email = session.get('pending_email')

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT email from users where email=%s and otp=%s",(email,otp))
            user = cursor.fetchone()
            if user:
                cursor.execute("UPDATE USERS SET is_active = 1, otp=NULL where email=%s",(email,))
                session.pop('pending_email')
                conn.commit()
                cursor.close()
                conn.close()
                flash("Email Verified...! Please Login...!",'success')
                return redirect(url_for('login'))
            else:
                flash('Incorrect otp, Please try again...!','error')
                return redirect(url_for('verify_otp'))
            cursor.close()
            conn.close()
        except Error as err:
            flash(f"Database Error:{err}",'error')
            return redirect(url_for('verify_otp'))
    return render_template('verify_otp.html')

@app.route('/resend-otp')
def resend_otp():
    email = session.get('pending_email')
    if not email:
        return redirect(url_for('register'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        otp = generate_otp()
        cursor.execute("UPDATE USERS SET otp=%s where email=%s",(otp,email))
        conn.commit()

        email_body = f"""
        <h2>SNM - New OTP</h2>
        <p>Your new OTP is:</p>
        <h1 style="color: #667eea;">{otp}</h1>
        """
        send_email(to_email=email, subject='SNM - New OTP', body=email_body, html=True)

        cursor.close()
        conn.close()
        flash("New Otp is sent to email...!")
        return redirect(url_for('verify_otp'))
    except Error as err:
        flash(f"Database Error:{err}",'error')
        return redirect(url_for('verify_otp'))
    

# Login router
@app.route('/login',methods=['POST','GET'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method=='POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash("Email and Password are required fields...!","warning")
            return redirect(url_for('login'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * from users where email=%s",(email,))
            user = cursor.fetchone()

            cursor.close()
            conn.close()

            if user:
                if not user['is_active']:
                    session['pending_email'] = email
                    flash("Please verify your email...!",'warning')
                    return redirect(url_for('verify_otp'))

                validate_pw = bcrypt.checkpw(password.encode('utf-8'),user['password'].encode('utf-8'))
        
                if validate_pw:
                    session.permanent = True
                    session['user_id'] = user['id']
                    session['user_name'] = user['name']
                    session['email'] = user['email']

                    flash('Login Successful...!','success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid password...! Please try again...!','warning')
                    return redirect(url_for('login'))
            else:
                flash('Invalid user...! Please register...!','warning')
                return redirect(url_for('register'))
        
        except Error as err:
            flash(f"Database Error:{err}",'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        session.pop('user_id',None)
        session.pop('user_name',None)
        session.pop('email',None)
        flash('logout successful...!','success')
        return redirect(url_for('login'))
    else:
        return redirect(url_for('home'))


@app.route('/forgot-password',methods=['GET','POST'])
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method=='POST':
        email = request.form.get('email')

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT email from users where email=%s",(email,))
            user = cursor.fetchone()

            cursor.close()
            conn.close()

            if user:
                token = generate_reset_token(email)
                reset_link = url_for('reset_password', token=token, _external=True)

                email_body = f"""
                            <h2>Password Reset Request</h2>
                <p>Click the link below to reset your password:</p>
                <a href="{reset_link}" style="background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a>
                <p>This link will expire in 1 hour.</p>
                <p>If you didn't request this, please ignore this email.</p>
                            """
                subject = "SNM - Password Reset"
                send_email(email,subject,email_body,html=True)
                flash('Password Reset is sent to mail....!','success')
                return redirect(url_for('login'))
            else:
                flash("User not registered with us...! Please register...!",'warning')
                return redirect(url_for('register'))
            
        except Error as err:
            flash(f"Database Error:{err}",'error')
            return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>',methods=['GET','POST'])
def reset_password(token):
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    check_token_email = verify_reset_token(token=token,expiration=300)
    if not check_token_email:
        flash('Reset link not Valid...! Please request again...!')
        return redirect(url_for('forgot_password'))
    
    if request.method=="POST":
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if  not password or not confirm_password:
            flash("All fields required!")
            return redirect(url_for('reset_password',token=token))
        
        if len(password)<6:
            flash("Password length must be greater 6-Characters...!")
            return redirect(url_for('reset_password',token=token))

        if password!=confirm_password:
            flash("Password and Confirm Password Do not match.")
            return redirect(url_for('reset_password',token=token))

        try :
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Hash password with bcrypt
            hashed_pw = bcrypt.hashpw(password.encode('utf-8'),bcrypt.gensalt())

            cursor.execute("UPDATE users SET password=%s WHERE email=%s",(hashed_pw.decode('utf-8'),check_token_email))

            conn.commit()

            cursor.close()
            conn.close()
            flash('Password Reset Successful...! Login Again...!','success')
            return redirect(url_for('login'))
        except Error as err:
            flash(f"Database Error:{err}",'error')
            return redirect(url_for('reset_password',token=token))
        
    return render_template('reset_password.html',token=token)


@app.route('/dashboard')
@login_required
def dashboard():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        user_id = session.get('user_id')

        cursor.execute("SELECT count(*) as notes_count from notes where user_id=%s",(user_id,))
        notes_count = cursor.fetchone()['notes_count']

        cursor.execute("SELECT count(*) as files_count from files where user_id=%s",(user_id,))
        files_count = cursor.fetchone()['files_count']

        cursor.execute("SELECT n.*,(SELECT count(*) from files f where f.note_id = n.id)  as files_count from notes n where user_id=%s ORDER BY n.created_at DESC LIMIT 3",(session.get('user_id'),))
        
        notes = cursor.fetchall()

        cursor.close()
        conn.close()

    except Error as err:
        flash(f"Database Error:{err}",'error')
        return redirect(url_for('dashboard'))
    
    return render_template('dashboard.html',notes_count=notes_count,files_count=files_count,notes=notes)

@app.route('/notes')
@login_required
def notes():

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT n.*,(SELECT count(*) from files f where f.note_id = n.id)  as files_count from notes n where user_id=%s ORDER BY n.created_at DESC",(session.get('user_id'),))

        notes = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template('notes.html',notes=notes)


    except Error as err:
        flash(f"Database Error:{err}",'error')
        return render_template('notes.html',notes=[])
    

@app.route('/notes/add',methods=['GET','POST'])
@login_required
def add_note():
    if request.method=='POST':
        title = request.form.get('title')
        description = request.form.get('description')

        if not title and not description:
            flash("Title and description fields are required...!",'warning')
            return redirect(url_for('add_note'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute('INSERT INTO notes (user_id,title,description) VALUES (%s,%s,%s)',(session.get('user_id'),title,description))

            conn.commit()
            cursor.close()
            conn.close()

            flash("Note Created successfully...!",'success')

            return redirect(url_for('notes'))


        except Error as err:
            flash(f"Database Error:{err}",'error')
            return redirect(url_for('add_note'))


    return render_template('add_note.html')

@app.route('/view-note/<int:note_id>')
@login_required
def view_note(note_id):

    try :
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * from notes where id = %s AND user_id=%s",(note_id,session.get('user_id')))

        note = cursor.fetchone()
        if not note:
            flash('Note not found or access denied...!','error')
            cursor.close()
            conn.close()
            return redirect(url_for('notes'))

        cursor.execute('SELECT * from files where note_id=%s and user_id=%s',(note_id,session.get('user_id')))

        attached_files = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template('view_note.html',note=note,attached_files=attached_files)
    
    except Error as err:
        flash(f"Database Error:{err}",'error')
        return redirect(url_for('notes'))
    

@app.route('/edit-note/<int:note_id>',methods=['GET','POST'])
@login_required
def edit_note(note_id):

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * from notes where id=%s and user_id=%s",(note_id,session.get('user_id')))
        
        note = cursor.fetchone()

        if not note:
            flash('Note not found or access denied...!','error')
            cursor.close()
            conn.close()
            return redirect(url_for('notes'))

        
        if request.method=='POST':
            title = request.form.get('title')
            description = request.form.get('description')
    
            if not title and not description:
                flash("Title and description fields are required...!",'warning')
                return redirect(url_for('edit_note',note_id=note_id))
           
            cursor.execute('UPDATE notes set title=%s,description=%s where id=%s and user_id=%s',(title,description,note_id,session.get('user_id')))
            conn.commit()
            cursor.close()
            conn.close()
            flash("Note updated successfully...!",'success')
            return redirect(url_for('view_note',note_id=note_id))

        cursor.close()
        conn.close()
        return render_template('edit_note.html',note=note)
        

    except Error as err:
        flash(f"Database Error:{err}",'error')
        return redirect(url_for('notes'))

@app.route('/delete-note/<int:note_id>')
@login_required
def delete_note(note_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("DELETE from notes where id=%s and user_id=%s",(note_id,session.get('user_id')))
        conn.commit()

        if cursor.rowcount > 0:
            flash('Note Deleted Successfully...!','success')
        else:
            flash('Note not found or Access denied...!','error')

        cursor.close()
        conn.close()
    except Error as err:
        flash(f"Database Error:{err}",'error')
        return redirect(url_for('notes'))
    
    return(redirect(url_for('notes')))    

@app.route('/files/upload',methods=["GET","POST"])
@login_required
def upload_file():
    if request.method=='POST':
        if 'file' not in request.files:
            flash("No file is Selected....!",'error')
            return redirect(request.url)

        file = request.files['file']
        note_id = request.form.get('note_id') or None
        file_name = file.filename

        if file_name=='':
            flash('No file is selected..!','error')
            return (request.url)

        if file and allowed_file(file_name):
            file_name = secure_filename(filename=file_name)

            file_path = os.path.join(app.config['UPLOAD_FOLDER'],file_name)
            counter = 1
            name,ext = os.path.splitext(file_name)
            while os.path.exists(file_path):
                file_name = f"{name}_{counter}{ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'],file_name)
                counter+=1

            file.save(file_path)

            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("INSERT INTO files (user_id,note_id,filename,filepath) values (%s,%s,%s,%s)",(session.get('user_id'),note_id,file_name,file_path))

                conn.commit()
                cursor.close()
                conn.close()

                flash("File uploaded successfully",'success')
                return redirect(url_for('files'))
            except Error as err:
                flash(f'Database error: {err}','error')  
                return redirect(url_for('files'))
        else:
            flash("File type not allowed...!",'error')
            return redirect(url_for('files'))
    else:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id,title from notes where user_id=%s",(session.get('user_id'),))
            notes = cursor.fetchall()
            cursor.close()
            conn.close()
        except Error as err:
            notes = []
            flash(f'Database error: {err}','error')
        return render_template('upload_file.html',notes=notes)

@app.route('/files')
@login_required
def files():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT f.*,n.title as note_title from files f LEFT JOIN notes n on f.note_id=n.id where f.user_id=%s order by f.created_at DESC",(session.get("user_id"),))
        files = cursor.fetchall()
        print(files)
        cursor.close()
        conn.close()

    except Error as err:
        files = []
        flash(f'Database error: {err}','error')
        

    return render_template('files.html',files=files)

@app.route('/files/delete/<int:file_id>')
@login_required
def delete_file(file_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * from files where id=%s and user_id=%s",(file_id,session.get('user_id')))

        file = cursor.fetchone()
        if not file:
            cursor.close()
            conn.close()
            flash('file not found or Access denied...!','error')
            return redirect(url_for('files'))
        else:
            if os.path.exists(file['filepath']):
                os.remove(file['filepath'])

            cursor.execute("DELETE FROM files where id=%s",(file_id,))
            conn.commit()
            flash("File deleted successfully...!",'success')
            cursor.close()
            conn.close()
            return redirect(url_for('files'))
        
    except Error as err:
        flash(f"Database Error: {err}")
        return redirect(url_for('files'))

@app.route('/view-file/<int:file_id>')
@login_required
def view_file(file_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * from files where id=%s and user_id=%s",(file_id,session.get('user_id')))

        file = cursor.fetchone()
        cursor.close()
        conn.close()

        if file and os.path.exists(file['filepath']):
            return send_file(file['filepath'])

        flash('file not found...!','error')
    except Error as err:
        flash(f"Database Error: {err}")

    return redirect(url_for('files'))



@app.route('/download-file/<int:file_id>')
@login_required
def download_file(file_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * from files where id=%s and user_id=%s",(file_id,session.get('user_id')))

        file = cursor.fetchone()
        cursor.close()
        conn.close()

        if file and os.path.exists(file['filepath']):
            return send_file(file['filepath'],as_attachment=True,download_name=file['filename'])

        flash('file not found...!','error')
    except Error as err:
        flash(f"Database Error: {err}")

    return redirect(url_for('files'))


@app.route('/search',methods = ['GET','POST'])
@login_required
def search():

    results = None
    query = None

    if request.method=='POST':
        query = request.form.get('query')

        if not re.match(r'^[\w\s]+$',query):
            flash('Invalid search query...! Use only Letters, Numbers, and Spaces.','error')
            return redirect(url_for('search'))
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            search_pattern = f"%{query}%"
            
            cursor.execute("SELECT * from notes where user_id=%s AND (title LIKE %s or description LIKE %s) order by created_at DESC",(session.get('user_id'),search_pattern,search_pattern))
            results = cursor.fetchall()

            cursor.close()
            conn.close()

        except Error as err:
            results = []
            flash(f"Database Error:{err}")
    return render_template('search.html',results=results,query=query)


if __name__ == '__main__':
    # Initialize database before starting the app
    if init_database():
        print("Starting Flask application...")
        print("Access the app at: http://127.0.0.1:5000")
        print("-"*50)
        app.run(debug=True, host='0.0.0.0',port=5000)
    else:
        print("\n" + "!"*50)
        print("Application could not start due to database errors.")
        print("Please fix the issues above and try again.")
        print("!"*50)