class User:
    def __init__(self, email, password, full_name, user_id, user_token, role='user', id=None):
        self.id = id
        self.email = email
        self.password = password
        self.full_name = full_name
        self.user_id = user_id
        self.user_token = user_token
        self.role = role
        

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
