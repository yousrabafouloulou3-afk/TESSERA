import streamlit as st
from views.shared import tr

def show():
    st.title(tr("❓ Help & FAQ"))
    st.markdown(tr("Welcome to the Help Center. Click on a question below to reveal the answer."))
    st.write("---")
    with st.expander(tr("Q: What is the Global Resource Checker?")):
        st.write(tr("A: It's a tool available to all users that allows you to check if a specific room is free at any given time slot across the entire university."))
        
    role = st.session_state.user.get('role', 'student')
    
    if role == 'delegate':
        with st.expander(tr("Q: How do I handle swap requests from professors?")):
            st.write(tr("A: As a delegate, your Dashboard will show pending swap requests for your section. You can Approve or Reject them on behalf of the students."))
        with st.expander(tr("Q: In which cases will a request be sent to me?")):
            st.write(tr("A: A request is sent to you whenever a professor asks to swap or reschedule a session, in the case where there is a group (or groups) affected by this change. You must review it on behalf of your classmates."))
        with st.expander(tr("Q: What happens if a request requires two delegates, and one accepts but the other rejects?")):
            st.write(tr("A: The request requires unanimous approval. If even one delegate rejects it, the entire request is rejected and the schedule will not change."))
        with st.expander(tr("Q: What happens if I reject a swap?")):
            st.write(tr("A: The professor's request will be marked as rejected and the schedule will not change."))
            
    elif role == 'teacher':
        with st.expander(tr("Q: How do I submit my module preferences?")):
            st.write(tr("A: During the preference submission window, use the '⭐ Top 3 Preferences' tab on your Dashboard to declare your preferred time slots for the modules you are assigned to teach."))
        with st.expander(tr("Q: How do I request a room or time swap?")):
            st.write(tr("A: On your Dashboard, navigate to the '🤝 Session Swaps' tab and use the '➕ Propose New Swap' feature. You can also use the '📅 Request Reschedule / Move Session' tab to move your session to an empty room. If the change affects students, their delegate will need to approve it."))
        with st.expander(tr("Q: When can I submit an Unavailability Request?")):
            st.write(tr("A: You can submit unavailability requests at any time before the preference deadline passes. Unlike module preferences, you can even submit them before the submission window officially opens!"))
        with st.expander(tr("Q: What is the AI Assistant?")):
            st.write(tr("A: When requesting a swap, you can use the AI Smart Match to automatically find the best available slots based on constraints and availability."))
        with st.expander(tr("Q: Can I cancel a swap or reschedule request I made by mistake?")):
            st.write(tr("A: Yes, as long as the request is still pending. Go to your 'My Swap Requests Log' or 'My Reschedule Requests Log', select the pending request from the dropdown, and click 'Cancel Request'."))
        with st.expander(tr("Q: What is the difference between Rescheduling and Swapping?")):
            st.write(tr("A: Rescheduling is moving your session to a completely empty room at a new time. Swapping is exchanging your session time and room with another professor's assigned session."))
        with st.expander(tr("Q: Do I need to declare preferences for every module I teach?")):
            st.write(tr("A: Yes, you should submit your Top 3 preferences for all modules assigned to you before the deadline. If you miss the deadline, the system will auto-generate random preferences for you to ensure the timetable can still be built."))
        with st.expander(tr("Q: What happens if I try to swap a TD with a Lecture (Cours)?")):
            st.write(tr("A: The system will warn you about a capacity conflict because TD rooms are usually too small for Lectures. You will be prompted to suggest an alternative Amphi for the swap to be valid."))
            
    elif role == 'admin':
        with st.expander(tr("Q: How do I generate the master timetable?")):
            st.write(tr("A: Go to the 'AI Engine & Analytics' tab and run the Optimization Engine. It will assign sessions while respecting all constraints."))
        with st.expander(tr("Q: What does 'modules with auto-generated fallbacks' mean?")):
            st.write(tr("A: It means the system automatically generated random module preferences for professors who failed to submit them before the deadline. This allows the AI Engine to proceed."))
        with st.expander(tr("Q: When do I use 'Override & Force Fallback'?")):
            st.write(tr("A: You use it when the preference submission deadline hasn't ended yet, but you need to generate the timetables immediately. It stops the countdown and generates random preferences for anyone who hasn't submitted them."))
        with st.expander(tr("Q: How do I remove auto-generated fallbacks?")):
            st.write(tr("A: You can click the 'Undo Override & Delete Fallbacks' button. This only clears the random preferences generated by the system, allowing you to restart the deadline and give professors who missed it another chance. Don't worry, the preferences submitted by other professors will remain perfectly intact and won't be deleted."))
        with st.expander(tr("Q: When should I re-click on 'Build Schedule'?")):
            st.write(tr("A: You should rebuild the schedule whenever you change an AI optimization weight to try and get a better result, or whenever you modify any underlying data (such as adding a new professor, room, or section)."))
        with st.expander(tr("Q: How do I view all timetables?")):
            st.write(tr("A: Use the 'Timetables View' tab to browse schedules by Section, Professor, Room, or Module."))
        with st.expander(tr("Q: How do I handle teacher requests?")):
            st.write(tr("A: The 'Approval Dashboard' allows you to review and approve or reject unavailability and reschedule requests submitted by teachers."))
        with st.expander(tr("Q: Do I have to approve every single swap request?")):
            st.write(tr("A: If a swap or reschedule request affects students, it must first be approved by the Section Delegate(s). Only after the delegates approve it will it appear on your Approval Dashboard for final confirmation."))
        with st.expander(tr("Q: What should I do if the AI Engine says it cannot find a solution?")):
            st.write(tr("A: This usually means the constraints are too tight. Try adding more available rooms, adjusting the optimization weights, or asking teachers to loosen their unavailability requests, then Rebuild the Schedule."))
        with st.expander(tr("Q: How do I delete a room, professor, or module/session from the database?")):
            st.write(tr("A: To delete any item (room, professor, or module/session), simply go to its text box in the Administrative Data Entry grid, delete its name (leave the box completely blank), and click Save. The system will delete that item from the database, safely clean up/unassign all related scheduled slots in the timetables, and shift the remaining items up automatically."))
    
    st.write("---")
    st.caption(tr("If your question isn't answered here, please contact support."))
