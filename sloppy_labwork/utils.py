import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


class SlEmail():
    def __init__(self,
                 from_email='no-reply@sloppylabwork.com',
                 to_emails='',
                 subject='',
                 html_content=''):
        self.message = Mail(from_email=from_email,
                            to_emails=to_emails,
                            subject=subject,
                            html_content=html_content)

    def send(self):
        client = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        return client.send(self.message)


class NewDeckRegistrationSubmittedEmail(SlEmail):
    def __init__(self, registration):
        super().__init__(to_emails=os.environ.get('REGISTER_VERIFIER_EMAIL'),
                         subject=self.get_subject(registration),
                         html_content=self.get_html_content(registration))

    def get_subject(self, registration):
        return 'New Registration Submitted - {}'.format(registration.deck.name)

    def get_html_content(self, registration):
        return """
          <p>
            A new deck registration request for {} has been submitted!
          </p>
          <p>
            You can review this registration <a href="https://sloppylabwork.com/admin/register/deckregistration/{}/change/">here</a>.
          </p>
        """.format(registration.deck.name, registration.id)
