from random import randrange
from sqlalchemy import create_engine
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import requests


class BotVk:

    def __init__(self, vk_token):
        self.vk_token = vk_token
        self.group_token = 'bfe1024c25a0d057f0ee08bcbbb8456e0caf85b21dc90750ac3b986a8d079bdd60293c45273cf8b6c4921'
        self.vk = vk_api.VkApi(token=self.group_token)
        self.longpoll = VkLongPoll(self.vk)
        engine = create_engine('postgresql://test_user:test@localhost:5432/test_task')
        self.connection = engine.connect()
        self.connection.execute("""CREATE TABLE IF NOT EXISTS users (id integer primary key);""")

    def check_city(self, city):
        response = requests.get("https://api.vk.com/method/database.getCities",
                                params={"access_token": self.vk_token, "v": "5.131", 'country_id': 1, 'q': city})
        for item in response.json()['response']['items']:
            if city == item['title']:
                self.city = item['id']
                return True
        return False

    def get_user_info(self, id):
        response = requests.get("https://api.vk.com/method/users.get",
                                params={"access_token": self.vk_token, "v": "5.131", "user_ids": id,
                                        'fields': 'bdate, sex, relation, city'})
        if 'error' not in response.json():
            self.id = response.json()['response'][0]['id']
            self.name = response.json()['response'][0]['first_name']
            if 'city' in response.json()['response'][0]:
                self.city = response.json()['response'][0]['city']['id']
            if 'sex' in response.json()['response'][0]:
                self.sex = response.json()['response'][0]['sex']
            if 'relation' in response.json()['response'][0]:
                self.relation = response.json()['response'][0]['relation']
            return True
        else:
            return False

    def get_id(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    id = event.text
                    if self.get_user_info(id) or id.lower() == 'назад':
                        return True
                    else:
                        self.write_msg(event.user_id, f"Такого пользователя не существует. Введите еще раз")

    def search_users(self):
        if self.sex == 2:
            gender = self.sex - 1
        else:
            gender = self.sex + 1
        response = requests.get("https://api.vk.com/method/users.search",
                                params={"access_token": self.vk_token, "v": "5.131", "count": "1000",
                                        'has_photo': '1', 'sex': gender, 'status': self.relation,
                                        'city': self.city, 'age_from': self.age - 5, 'age_to': self.age + 5})
        response.raise_for_status()
        users_list = response.json()['response']['items']
        _list = [(user['id'], user['first_name'],
                  user['last_name']) for user in users_list if user['is_closed'] == False]

        return _list

    def check_id_in_base(self, user_id):
        list_of_id = self.connection.execute(f"""SELECT id FROM users;""").fetchall()
        for id in list_of_id:
            if id[0] == user_id:
                return False
        else:
            return True

    def upload_to_base(self, user_id):
        if self.check_id_in_base(user_id):
            self.connection.execute(f"""INSERT INTO users VALUES ({user_id});""")

    def get_action(self, user_id):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.lower() == 'назад':
                        del self.sex
                        del self.city
                        del self.relation
                        del self.age
                        self.write_msg(event.user_id, f'Обращайтесь еще)')
                        return True
                    elif request.lower() == '+':
                        self.upload_to_base(user_id)
                        return False
                    else:
                        return False

    def show_users(self, event):
        users = self.search_users()
        for user_id, first_name, last_name in users:
            if self.check_id_in_base(user_id):
                photos_list = []
                response = requests.get("https://api.vk.com/method/photos.get", params={"access_token": self.vk_token,
                                                                                        "owner_id": user_id,
                                                                                        "v": "5.131",
                                                                                        "album_id": "profile",
                                                                                        "extended": "1"})
                photos = response.json()['response']['items']
                for photo in photos:
                    media_id = photo['id']
                    likes = photo['likes']['count']
                    comments = photo['comments']['count']
                    url = photo['sizes'][-1]['url']
                    new_tuple = (likes, comments, media_id, url)
                    photos_list.append(new_tuple)
                max_3_photos = sorted(photos_list, key=lambda x: (x[0], x[1]), reverse=True)[:3]
                for m_p in max_3_photos:
                    self.vk.method('messages.send', {'user_id': event.user_id, "attachment": f'photo{user_id}_{m_p[2]}',
                                                     'random_id': 0})
                user_url = f'https://vk.com/id{user_id}'
                self.write_msg(event.user_id, f"{first_name} {last_name} {user_url}")
                self.write_msg(event.user_id, f'Введите "+", чтобы добаить в избраное и продолжить '
                                              f'или любой символ для продолжения без сохранения, '
                                              f'или "Назад" - чтобы закончить')
                if self.get_action(user_id):
                    break

    def write_msg(self, user_id, message):
        return self.vk.method('messages.send', {'user_id': user_id, 'message': message,
                                                'random_id': randrange(10 ** 7), })

    def get_city(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if self.check_city(request):
                        break
                    else:
                        self.write_msg(event.user_id, f"Вы ввели пустую строку. Попробуйте еще раз:")

    def get_age(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.isdigit() and int(request) < 100:
                        self.age = int(request)
                        break
                    else:
                        self.write_msg(event.user_id, f"Вы ввели не правильный возраст. Попробуйте еще раз:")

    def get_sex(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.isdigit() and 0 < int(request) < 3:
                        self.sex = int(request)
                        break
                    else:
                        self.write_msg(event.user_id, f"Вы ввели не правильный пол. Попробуйте еще раз:")

    def get_relation(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.isdigit() and 0 < int(request) < 8:
                        self.relation = int(request)
                        break
                    else:
                        self.write_msg(event.user_id, f"Вы ввели не правильный статус. Попробуйте еще раз:")

    def sender(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.lower() in ['здарова', 'здравствуй', 'здравствуйте', 'привет', 'хай', 'hello', 'hi']:
                        self.write_msg(event.user_id, f"Привет, Дорогой пользователь. Для кого будем искать вторую "
                                                      f"половинку?) Мне нужен номер id или никнейм")
                        if self.get_id():

                            if 'city' not in self.__dict__:
                                self.write_msg(event.user_id, f"Введите город:")
                                self.get_city()
                            if 'age' not in self.__dict__:
                                self.write_msg(event.user_id, f"Введите возраст:")
                                self.get_age()
                            if 'sex' not in self.__dict__:
                                self.write_msg(event.user_id, f"""
                                Укажите цифру соответствующую полу:
                                1 - женский
                                2 - мужской""")
                                self.get_sex()
                            if 'relation' not in self.__dict__:
                                self.write_msg(event.user_id, f"""
                                Укажите цифру соответствующую семейному статусу:
                                1 — не женат (не замужем);
                                2 — встречается;
                                3 — помолвлен(-а);
                                4 — женат (замужем);
                                5 — всё сложно;
                                7 — влюблен(-а);
                                8 — в гражданском браке.""")
                                self.get_relation()

                            self.show_users(event)

                    elif request.lower() == "пока":
                        self.write_msg(event.user_id, "Пока((")
                    else:
                        self.write_msg(event.user_id, "Не поняла вашего ответа...")


if __name__ == '__main__':
    b = BotVk('958eb5d439726565e9333aa30e50e0f937ee432e927f0dbd541c541887d919a7c56f95c04217915c32008')
    b.sender()
