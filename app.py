from flask import Flask,url_for,redirect,request

app = Flask(__name__) # to intialize the application 

@app.route("/")
def home():
    return "Welcome to Flask world"

@app.route("/about")
def about():
    return "Welcome to About Page"

@app.route("/information")
@app.route("/info")
def info():
    return "Welcome to info Page"

@app.route("/info/<string:name>/<int:place>")
def information(name,place):
    a = type(name)
    b = type(place)
    print(a)
    print(type(place))
    return f"Hey {name}! Welcome to {place}. The data type name is {a}"

# Url converter : string,int,float,path,uuid

@app.route("/info/<float:percentage>")
def info1(percentage):
    print(type(percentage))
    return f"Your percentage is {percentage}"

@app.route("/info/path/<path:percentage>")
def info2(percentage):
    print(type(percentage))
    return f"Your percentage is {percentage}"

@app.route("/info/<uuid:percentage>")
def info3(percentage):
    print(type(percentage))
    return f"Your percentage is {percentage}"

@app.route("/info/<int:percentage>/name")
def info4(percentage):
    if percentage==1:
        a = url_for("info")
        print(a)
        return redirect("/info")
    return f"Your percentage is {percentage}"

@app.route("/info/<int:percentage>")
def info5(percentage):
    if percentage==1:
        return redirect(url_for("info"))
    return f"Your percentage is {percentage}"

@app.route("/details",methods=['POST'])
def details():

# when we want to create new record in db or else when we want handle the larger payload to the backend

   a = request.args.get("name")
   b = request.args.get("place")
   
#    a = request.get_json()
#    b = a['name']
#    c = a['place']

#    a = request.form.get("name")
#    b = request.form.get("place")


   return f"Hey {a}! Welcome to {b}"

@app.route("/detail",methods=['PUT','PATCH'])
def detail():

# when we want to modify the existing record in db -- PUT Method
# when we want add new field or new data to the existing record -- PATCH Method

   a = request.form.get("name")
   b = request.form.get("place")

   return f"Hey {a}! Welcome to {b} your data has been updated"

@app.route("/detail1",methods=['DELETE'])
def detail1():

# when we want to DELETE the existing record in db -- DELETE Method

   a = request.form.get("name")
   b = request.form.get("place")


   return f"Hey {a}! Welcome to {b} your data has been Deleted"


@app.route("/validationpost",methods=['POST','GET'])
def validation_post():
    if request.method=="POST":
        a = request.form.get("name")
        b = request.form.get("place",None)
        print(request.form)

        if a is None or a=='':
            return "Name is required field, Pls Enter the name value"
        if b is None or b=='':
            return "Place is required field, Pls Enter the Place value"
        
        return redirect(url_for("details",name=a,place=b,_method="POST"),code=307)
        

    return """
<form method="POST">
    <input type="text" name="name" placeholder="Enter Name"><br><br>
    <input type="text" name="place" placeholder="Enter Place"><br><br>
    <button type="submit">Submit</button>
</form>
"""
    

    




if __name__=="__main__":
    app.run(use_reloader=True,debug=True)