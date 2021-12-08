from random import randrange
from sqlalchemy import create_engine
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import requests


class Base:

    def __init__(self):
        engine = create_engine('postgresql://test_user:test@localhost:5432/test_task')
        self.connection = engine.connect()

    def create_table(self, owner_id):
        self.connection.execute(f"""CREATE TABLE IF NOT EXISTS user{owner_id} (id integer primary key);""")
        self.connection.execute(f"""CREATE TABLE IF NOT EXISTS user{owner_id}_photos (
                                        link text,
                                        user{owner_id}_id integer not null references user{owner_id}(id));""")

    def check_id_in_base(self, owner_id, user_id):
        list_of_id = self.connection.execute(f"""SELECT id FROM user{owner_id};""").fetchall()
        for id in list_of_id:
            if id[0] == user_id:
                return True
        else:
            return False

    def upload_id_to_table(self, owner_id, user_id):
        if not self.check_id_in_base(owner_id, user_id):
            self.connection.execute(f"""INSERT INTO user{owner_id} VALUES ({user_id});""")

    def upload_photo_to_table(self, owner_id, user_id, photo_link: str):
        self.connection.execute(f"""INSERT INTO user{owner_id}_photos VALUES ('{photo_link}', {user_id});""")

class VK:

    def __init__(self, vk_token):
        self.vk_token = vk_token

    def check_city(self, city):
        response = requests.get("https://api.vk.com/method/database.getCities",
                                params={"access_token": self.vk_token, "v": "5.131", 'country_id': 1, 'q': city})
        for item in response.json()['response']['items']:
            if city.lower() == item['title'].lower():
                return item['id']
        return False

    def get_nessesary_info(self, event):
        user_info = self.get_user_info(event.user_id)
        Bot().write_msg(event.user_id, f"Введите возраст:")
        user_info['age'] = Bot().get_age()
        if user_info['city'] == None:
            Bot().write_msg(event.user_id, f"Введите город:")
            user_info['city'] = Bot().get_city()
        if user_info['sex'] == None:
            Bot().write_msg(event.user_id, f"""
                                        Укажите цифру соответствующую полу:
                                        1 - женский
                                        2 - мужской""")
            user_info['sex'] = Bot().get_sex()
        if user_info['relation'] == None:
            Bot().write_msg(event.user_id, f"""
                                        Укажите цифру соответствующую семейному статусу:
                                        1 — не женат (не замужем);
                                        2 — встречается;
                                        3 — помолвлен(-а);
                                        4 — женат (замужем);
                                        5 — всё сложно;
                                        7 — влюблен(-а);
                                        8 — в гражданском браке.""")
            user_info['relation'] = Bot().get_relation()
        return user_info

    def get_user_info(self, id):
        response = requests.get("https://api.vk.com/method/users.get",
                                params={"access_token": self.vk_token, "v": "5.131", "user_ids": id,
                                        'fields': 'bdate, sex, relation, city'})
        if 'error' not in response.json():
            user_info = {}
            user_info['id'] = response.json()['response'][0]['id']
            user_info['name'] = response.json()['response'][0]['first_name']
            if 'city' in response.json()['response'][0]:
                user_info['city'] = response.json()['response'][0]['city']['id']
            else:
                user_info['city'] = None
            if 'sex' in response.json()['response'][0]:
                user_info['sex'] = response.json()['response'][0]['sex']
            else:
                user_info['sex'] = None
            if 'relation' in response.json()['response'][0]:
                user_info['relation'] = response.json()['response'][0]['relation']
            else:
                user_info['relation'] = None
            return user_info
        else:
            return False

    def search_users(self, user_info):
        if user_info['sex'] == 2:
            gender = user_info['sex'] - 1
        else:
            gender = user_info['sex'] + 1
        response = requests.get("https://api.vk.com/method/users.search",
                                params={"access_token": self.vk_token, "v": "5.131", "count": "1000",
                                        'has_photo': '1', 'sex': gender, 'status': user_info['relation'],
                                        'city': user_info['city'], 'age_from': user_info['age'] - 5,
                                        'age_to': user_info['age'] + 5})
        response.raise_for_status()
        users_list = response.json()['response']['items']
        _list = [(user['id'], user['first_name'],
                  user['last_name']) for user in users_list if user['is_closed'] == False]

        return _list

    def show_users(self, event, user_info):
        users = self.search_users(user_info)
        Base().create_table(event.user_id)
        for user_id, first_name, last_name in users:
            if not Base().check_id_in_base(event.user_id, user_id):
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
                    Bot().vk.method('messages.send',{'user_id': event.user_id, "attachment": f'photo{user_id}_{m_p[2]}',
                                                    'random_id': 0})
                user_url = f'https://vk.com/id{user_id}'
                Bot().write_msg(event.user_id, f"{first_name} {last_name} {user_url}")
                Bot().write_msg(event.user_id, f'Введите "+", чтобы добавить в избраное и продолжить '
                                              f'или любой символ для продолжения без сохранения, '
                                              f'или "Назад" - чтобы закончить')
                if Bot().get_action_2(user_id, max_3_photos) == False:
                    break

class Bot:

    def __init__(self):
        self.group_token = 'bfe1024c25a0d057f0ee08bcbbb8456e0caf85b21dc90750ac3b986a8d079bdd60293c45273cf8b6c4921'
        self.vk = vk_api.VkApi(token=self.group_token)
        self.longpoll = VkLongPoll(self.vk)
        self.vk_token = '958eb5d439726565e9333aa30e50e0f937ee432e927f0dbd541c541887d919a7c56f95c04217915c32008'

    def write_msg(self, user_id, message):
        return self.vk.method('messages.send', {'user_id': user_id, 'message': message,
                                                'random_id': randrange(10 ** 7), })

    def get_city(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text.lower()
                    city_id = VK(self.vk_token).check_city(request)
                    if city_id:
                        return city_id
                    else:
                        self.write_msg(event.user_id, f"Такого города в списке нет. Попробуйте еще раз:")

    def get_age(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.isdigit() and int(request) < 100:
                        return int(request)
                    else:
                        self.write_msg(event.user_id, f"Вы ввели не правильный возраст. Попробуйте еще раз:")

    def get_sex(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.isdigit() and 0 < int(request) < 3:
                        return int(request)
                    else:
                        self.write_msg(event.user_id, f"Вы ввели не правильный пол. Попробуйте еще раз:")

    def get_relation(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me:
                    request = event.text
                    if request.isdigit() and 0 < int(request) < 8:
                        return int(request)
                    else:
                        self.write_msg(event.user_id, f"Вы ввели не правильный статус. Попробуйте еще раз:")

    def get_action_2(self, user_id, photo_list):
        for event in self.longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW:
                    if event.to_me:
                        answer = event.text
                        if answer.lower() == '+':
                            Base().upload_id_to_table(event.user_id, user_id)
                            for photo in photo_list:
                                Base().upload_photo_to_table(event.user_id, user_id, photo[3])
                            return True
                        elif answer.lower() == 'назад':
                            message_id = event.message_id
                            self.write_msg(event.user_id, f"Приходи еще)))")
                            return False
                        else:
                            return True

    def get_action(self, word_1, word_2):
        for event in self.longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW:
                    if event.to_me:
                        request = event.text
                        if request.lower() == word_1:
                            return True
                        elif request.lower() == word_2:
                            return False
                        else:
                            self.write_msg(event.user_id, "Не поняла вашего ответа...")

    def sender(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                if event.to_me and event.text != 'назад':
                    request = event.text
                    if request.lower() in ['здарова', 'здравствуй', 'здравствуйте', 'привет', 'хай', 'hello', 'hi']:
                        self.write_msg(event.user_id,
                                f"Привет, Дорогой пользователь. Начнем поиск второй половинки? (Да или Нет)")
                        if self.get_action('да', 'нет'):
                            user_info = VK(self.vk_token).get_nessesary_info(event)
                            VK(self.vk_token).show_users(event, user_info)
                        else:
                            self.write_msg(event.user_id, f"Жаль, что уходите так быстро(((")
                    elif request.lower() == "пока":
                        self.write_msg(event.user_id, "Пока((")
                    else:
                        self.write_msg(event.user_id, "Не поняла вашего ответа...")


if __name__ == '__main__':
    b = Bot()
    b.sender()
