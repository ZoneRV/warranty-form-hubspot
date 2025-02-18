import json
from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'fallback_secret')

HUBSPOT_ACCESS_TOKEN  = os.environ.get('HUBSPOT_ACCESS_TOKEN')
HUBSPOT_TICKETS_URL = 'https://api.hubapi.com/crm/v3/objects/tickets'

@app.route('/', methods=['GET', 'POST'])
def warranty_form():
    if request.method == 'POST':
        # Collect form data
        customer_first_and_last_name = request.form['customer_first_and_last_name']
        email = request.form['email']
        van_number_build_spot = request.form.get('van_number_build_spot').strip()
        phone_number = request.form['phone_number']
        subjects = request.form.getlist('subject[]')  # All subjects
        contents = request.form.getlist('content[]')  # All contents
        upload_your_photos_1_of_3_s = request.files.getlist('upload_your_photos_1_of_3_[]')

        # Initialize a dictionary to store photos per claim
        photos_per_claim = {}
        for i in range(len(subjects) + 1):
            key = f"more_photos[{i}]"
            if key in request.files:
                photos_per_claim[i] = request.files.getlist(key)
            else:
                photos_per_claim[i] = []

        # Validate required fields
        if not all([customer_first_and_last_name, email, van_number_build_spot, phone_number, subjects, contents,
                    upload_your_photos_1_of_3_s]):
            flash('Please fill out all required fields.', "danger")
            return redirect(url_for('warranty_form'))

        # Validate initial uploaded photo
        if len(upload_your_photos_1_of_3_s) != len(subjects):
            flash('Number of required photos must match the number of claims.', 'danger')
            return redirect(url_for('warranty_form'))

            # Process each claim
        for i in range(len(subjects)):
            uploaded_photo = upload_your_photos_1_of_3_s[i]  # Safe because lengths are equal

            # Ensure the required photo is valid
            if not (uploaded_photo and allowed_file(uploaded_photo) and allowed_mime_type(uploaded_photo)):
                flash('Each claim requires a valid uploaded photo.', 'danger')
                return redirect(url_for('warranty_form'))

        # Validate and process additional photos
        for i, claim_photos in photos_per_claim.items():
            for file in claim_photos:
                if file and file.filename:
                    if not allowed_file(file) or not allowed_mime_type(file):
                        flash('Please upload a valid image file.', "danger")
                        return redirect(url_for('warranty_form'))

        customer_first, customer_last = customer_first_and_last_name.split(" ", 1)
        contact_id = get_contact_id_by_email(email)

        if not contact_id:
            contact_id = create_contact(email, customer_first, customer_last, phone_number)

        if not contact_id:
            flash("Failed to create or find contact. Cannot proceed with warranty claim.", "danger")
            return redirect(url_for('warranty_form'))

        # Create tickets for each claim
        for i in range(len(subjects)):
            uploaded_photo = upload_your_photos_1_of_3_s[i]

            # Prepare the properties for the ticket
            uploaded_photo_url = None
            if uploaded_photo and uploaded_photo.filename:  # Ensure file was uploaded
                uploaded_photo_url = upload_file_to_hubspot(uploaded_photo)
                if not uploaded_photo_url:
                    flash('Failed to upload photo to HubSpot.', "danger")
                    return redirect(url_for('warranty_form'))

            # Prepare the properties for the ticket
            data = {
                "properties": {
                    "hs_pipeline": "40278638",  # pipeline ID
                    "hs_pipeline_stage": "85346662",  # Corrected to lowercase
                    "customer_first_and_last_name": customer_first_and_last_name,
                    "van_number_build_spot": van_number_build_spot,
                    "subject": str(subjects[i]) if subjects else "No Subject Provided",
                    "content": str(contents[i]) if contents else "No Content Provided",
                    "upload_your_photos_1_of_3_": uploaded_photo_url,
                }
            }

            # Upload the ticket to HubSpot
            headers = {
                "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }
            response = requests.post(HUBSPOT_TICKETS_URL, json=data, headers=headers)

            if response.status_code == 201:
                ticket_data = response.json()
                ticket_id = ticket_data.get("id")  # Get the created ticket ID
                flash("Warranty claim submitted successfully!", "success")
                associate_contact_to_ticket(contact_id, ticket_id)

                photo_ids = []
                # Upload additional photos for this claim
                if photos_per_claim[i]:
                    for file in photos_per_claim[i]:
                        if file and file.filename:
                            if not allowed_file(file) or not allowed_mime_type(file):
                                flash('Please upload a valid image file.', "danger")
                                return redirect(url_for('warranty_form'))

                            file_url = upload_file_to_hubspot(file)
                            if file_url:
                                photo_ids.append(file_url)

                # Update the ticket with additional photos
                update_ticket_properties(ticket_id, photo_ids)

            else:
                flash(f"An error occurred while submitting the warranty claim: {response.text}", "danger")
                print("Response:", response.json())  # Log full error response
                return redirect(url_for('warranty_form'))

    return render_template('warranty_form.html')

def get_contact_id_by_email(email):
    url = f"https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": email
                    }
                ]
            }
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            return results[0]["id"]  # Return the contact ID if found
    return None  # Contact not found

def create_contact(email, first_name, last_name, phone_number):
    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "properties": {
            "email": email,
            "firstname": first_name,
            "lastname": last_name,
            "phone": phone_number
        }
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json().get("id")  # Return new contact ID
    return None  # Failed to create contact

def associate_contact_to_ticket(contact_id, ticket_id):
    url = f"https://api.hubapi.com/crm/v3/associations/ticket/contact/batch/create"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "inputs": [
            {
                "from": {"id": ticket_id},
                "to": {"id": contact_id},
                "type": "ticket_to_contact"
            }
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code == 201  # Return True if association succeeded


def update_ticket_properties(ticket_id, file_urls):
    # This function updates the ticket with additional photo URLs
    update_url = f"https://api.hubapi.com/crm/v3/objects/tickets/{ticket_id}"

    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Get the current ticket properties
    response = requests.get(update_url, headers=headers)
    if response.status_code == 200:

        # Prepare the updated properties
        properties = {
            "more_photos": '; '.join(file_urls)  # Join the list into a comma-separated string
        }

        # Send the update request
        response = requests.patch(update_url, json={"properties": properties}, headers=headers)
        if response.status_code == 200:
            print(f"Ticket updated with new photo URL: {file_urls}")
        else:
            print(f"Failed to update ticket with new photo: {response.text}")
    else:
        print(f"Failed to retrieve ticket data for update: {response.text}")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'webm'}
ALLOWED_MIME_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'video/mp4', 'video/avi', 'video/quicktime', 'video/mov', 'video/webm'}

def allowed_file(file):
    return '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_mime_type(file):
    return file.mimetype in ALLOWED_MIME_TYPES

def upload_file_to_hubspot(file):
    file_upload_url = "https://api.hubapi.com/files/v3/files"  # File Upload API endpoint

    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}"  # Ensure token is valid with 'files' scope
    }

    # Prepare options; this can be extended if additional options are required by the API
    options_dict = {
        "access": "PRIVATE",  # Example option, adjust as necessary
        'ttl': 'P3M',
        "overwrite": True,
        'duplicateValidationStrategy': 'NONE',
        'duplicateValidationScope': 'EXACT_FOLDER'
    }

    options = json.dumps(options_dict)

    # Prepare the multipart data
    files = {
        "file": (file.filename, file.stream, file.mimetype),  # Use 'files' for multipart/form-data
    }

    # Prepare the form data
    data = {
        "folderPath": "/",
        "options": options  # Include options as a form field
    }

    # Debug: Inspect everything you're sending
    print("=== Debugging Payload ===")
    print("Headers:", headers)
    print("Options JSON:", options)
    print("Files Payload:", files)
    print("Form Data:", data)
    print("=========================")

    # Send the POST request with the correct multipart/form-data
    response = requests.post(file_upload_url, headers=headers, files=files, data=data)

    # Debugging: Print the response for troubleshooting
    if response.status_code in (200, 201):  # Successful response
        uploaded_file_data = response.json()
        file_url = uploaded_file_data.get("url")
        print(f"Uploaded file URL: {file_url}")
        return file_url
    else:
        print(f"Failed to upload file to HubSpot: {response.status_code}")
        print(response.text)
        return None



if __name__ == '__main__':
    app.run(debug=True)
