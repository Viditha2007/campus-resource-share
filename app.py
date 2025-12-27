import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud import storage
from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import LLMChain
from langchain_google_genai import GoogleGenerativeAI
import os

# ====================== PAGE CONFIG ======================
st.set_page_config(page_title="Campus Resource Share", page_icon="📚", layout="centered")

st.title("📚 Campus Resource Share")
st.markdown("*Sharing books, notes, and lab equipment across Hyderabad colleges with AI-powered recommendations*")

st.sidebar.title("About")
st.sidebar.info("**Hack Ananta 2025** | SDG 4: Quality Education")
st.sidebar.caption("Promoting equitable access to educational resources through collaboration.")
st.sidebar.markdown("---")
st.sidebar.caption("Powered by Google Firebase • Cloud Storage • Gemini AI")



# Safe Firebase initialization (handles Streamlit reruns perfectly)
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()
# === Google Cloud Storage ===
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "firebase_key.json"
storage_client = storage.Client()
bucket_name = "campus-resource-share-code"  # ← CHANGE THIS TO YOUR EXACT BUCKET NAME IF DIFFERENT
bucket = storage_client.bucket(bucket_name)

# === Gemini AI Key (Secure way using Streamlit secrets) ===
# Create a folder .streamlit in your project, then file secrets.toml inside it:
# GEMINI_API_KEY = "your_actual_key_here"
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("⚠️ Please add your Gemini API key to .streamlit/secrets.toml")
    st.stop()

llm = GoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GEMINI_API_KEY)

# ====================== AI AGENTS ======================
stitch_prompt = PromptTemplate(
    input_variables=["data"],
    template="""Clean and standardize this resource posting for better matching. 
Remove typos, format consistently, extract key details.
Input: {data}
Output only the cleaned version:"""
)
stitch_agent = LLMChain(llm=llm, prompt=stitch_prompt)

antigravity_prompt = PromptTemplate(
    input_variables=["data"],
    template="""Scan this resource posting for safety or privacy risks (personal info, inappropriate content, etc.): {data}
Respond with: APPROVED or REJECTED followed by a brief reason."""
)
antigravity_agent = LLMChain(llm=llm, prompt=antigravity_prompt)

gemini_prompt = PromptTemplate(
    input_variables=["query"],
    template="""Based on this resource: {query}
Suggest 3 similar resources a student might also need (books, notes, equipment).
Format as a numbered list."""
)
gemini_agent = LLMChain(llm=llm, prompt=gemini_prompt)

def process_resource_with_agents(resource_data):
    try:
        cleaned = stitch_agent.run(str(resource_data))
        safety = antigravity_agent.run(cleaned)
        if "rejected" in safety.lower():
            return f"❌ Rejected: {safety}"
        recommendations = gemini_agent.run(cleaned)
        return f"✅ Approved!\n\n**AI Recommendations:**\n{recommendations}"
    except Exception as e:
        return f"⚠️ Agent error: {str(e)}"

# ====================== AUTHENTICATION (Hackathon Mode) ======================
if 'user' not in st.session_state:
    st.subheader("🔐 Login / Signup (Demo Mode)")
    st.info("For demo: Use any email and password (6+ characters)")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Submit"):
        if len(password) < 6:
            st.error("Password must be at least 6 characters")
        elif email and password:
            st.success(f"Welcome, {email}!")
            st.session_state.user = {"email": email}
            st.rerun()
        else:
            st.error("Fill both fields")
else:
    st.success(f"Logged in as: {st.session_state.user['email']}")
    if st.button("Logout"):
        del st.session_state.user
        st.rerun()


if 'user' in st.session_state:
    st.markdown("---")
    st.subheader("📤 Share a Resource")

    with st.form("post_form"):
        title = st.text_input("Title*", placeholder="e.g., Introduction to Machine Learning by Andrew Ng")
        description = st.text_area("Description*", placeholder="Condition, edition, subjects covered...")
        category = st.selectbox("Category*", ["Books", "Notes", "Lab Equipment", "Other"])
        uploaded_file = st.file_uploader("Upload photo or PDF (optional)", type=["pdf", "jpg", "jpeg", "png"])  # ← Define here

        submitted = st.form_submit_button("Post Resource")

        if submitted:
            if not title or not description:
                st.error("Title and description are required.")
            else:
                file_url = ""
                if uploaded_file is not None:  # ← Check if file was actually uploaded
                    with st.spinner("Uploading file..."):
                        filename = f"{st.session_state.user['email'].split('@')[0]}_{uploaded_file.name}"
                        blob = bucket.blob(filename)
                        blob.upload_from_file(uploaded_file)
                        
                        # Generate signed URL
                        signed_url = blob.generate_signed_url(
                            version="v4",
                            expiration=timedelta(days=365),
                            method="GET"
                        )
                        file_url = signed_url
                        st.success("File uploaded securely!")
                else:
                    file_url = ""

                # Now create resource data (outside if/else)
                resource_data = {
                    "title": title,
                    "description": description,
                    "category": category,
                    "owner": st.session_state.user["email"],
                    "file_url": file_url,
                    "status": "available",
                    "timestamp": firestore.SERVER_TIMESTAMP
                }

                with st.spinner("Processing with AI agents..."):
                    db.collection("resources").add(resource_data)
                    ai_result = process_resource_with_agents(resource_data)

                st.success("Resource posted successfully!")
                st.info(ai_result)
# ====================== SEARCH & VIEW RESOURCES ======================
# ====================== SEARCH & VIEW RESOURCES ======================
st.markdown("---")
st.subheader(" Search Available Resources")

search_query = st.text_input("Search by title, category, or description")

resources = db.collection("resources").where("status", "==", "available").stream()

found = False
for doc in resources:
    data = doc.to_dict()
    search_text = f"{data['title']} {data['description']} {data['category']}".lower()
    
    if search_query.lower() in search_text or not search_query:
        found = True
        with st.container(border=True):
            st.markdown(f"""
### {data['title']}
**Category:** {data['category']} | **Owner:** {data['owner']}
""")
            st.write(data['description'])

            if data.get('file_url'):
                if data['file_url'].lower().endswith(('.jpg', '.jpeg', '.png')):
                    st.image(data['file_url'], width=300)
                else:
                    st.markdown(f"[Download File]({data['file_url']})")

            if st.button("Request this Resource", key=doc.id):
                db.collection("resources").document(doc.id).update({"status": "requested"})
                st.success("Request sent!")
                st.rerun()

if not found and search_query:
    st.info("No resources found matching your search.")
elif not search_query:
    st.info("Tip: Use the search box above to filter resources.")

# ====================== FOOTER ======================
st.markdown("---")

st.caption("Made with  for Hack Ananta 2025 | Aligning with **UN SDG 4: Quality Education**")
