from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def warranty_form():
    if request.method == 'POST':
        # Collect form data
        customer_name = request.form['customer_name']
        email = request.form['email']
        van_number = request.form['van_number']
        phone_number = request.form['phone_number']
        issue_summary = request.form['issue_summary']
        issue_explanation = request.form['issue_explanation']
        is_safe_to_use = request.form.get('is_safe_to_use', 'No')
        photos = request.files.get('photos')
        is_customer_copy_true = request.form.get('is_customer_copy_true', 'No')

        # Here you would normally save the form data to a database
        # For now, let's print it to the console
        print(f'Warranty claim received from {customer_name}')
        print(f'Email: {email}, Van Number: {van_number}, Phone Number: {phone_number}')
        print(f'Issue Summary: {issue_summary}')
        print(f'Elaborate Explanation: {issue_explanation}')
        print(f'Is it safe to use: {is_safe_to_use}')
        print(f'Photos: {photos}')
        print(f'Is customer copy true: {is_customer_copy_true}')

        return "Warranty claim submitted successfully!"

    return render_template('warranty_form.html')

if __name__ == '__main__':
    app.run(debug=True)
