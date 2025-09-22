import json
import re
from math import radians, sin, cos, sqrt, atan2
from telegram import Update, Location
from telegram.ext import CallbackContext, MessageHandler, filters

# Гаверсин формуласы арқылы екі нүкте арасындағы қашықтықты есептеу (км)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0  # Жердің радиусы километрмен

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance

# 2GIS сілтемесінен координаттарды алу
def extract_coords_from_2gis_link(link):
    # 'm=' параметрінен кейінгі сандарды іздейміз
    match = re.search(r'm=([\d.]+),([\d.]+)', link)
    if match:
        # 2GIS сілтемесінде бірінші longitude, сосын latitude келеді
        lon, lat = map(float, match.groups())
        return lat, lon
    return None, None

# Локацияны өңдейтін негізгі функция
def location_handler(update: Update, context: CallbackContext):
    user_location: Location = update.message.location
    user_lat = user_location.latitude
    user_lon = user_location.longitude

    update.message.reply_text("Халал мекемелерді іздеп жатырмын, сәл күте тұрыңыз...")

    try:
        # JSON файлын ашу (файлдың дұрыс жолын көрсетіңіз)
        with open('qmdb_data_json.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        update.message.reply_text("Кешіріңіз, мекемелер базасы табылмады.")
        return
    except json.JSONDecodeError:
        update.message.reply_text("Кешіріңіз, деректер базасының форматы дұрыс емес.")
        return
        
    organizations = data['data']['organizations']
    nearby_establishments = []

    for org in organizations:
        # `maplink` массивіндегі бірінші сілтемені аламыз
        if org.get('maplink') and len(org['maplink']) > 0 and 'link' in org['maplink'][0]:
            map_link = org['maplink'][0]['link']
            lat, lon = extract_coords_from_2gis_link(map_link)
            
            if lat and lon:
                distance = calculate_distance(user_lat, user_lon, lat, lon)
                
                # Қашықтығы 100 км-ден аз мекемелерді ғана қосамыз (қалауыңызша өзгертуге болады)
                if distance < 100:
                    org['distance'] = distance
                    nearby_establishments.append(org)

    # Мекемелерді қашықтығы бойынша сұрыптау
    sorted_establishments = sorted(nearby_establishments, key=lambda x: x['distance'])
    
    # Алғашқы 5 мекемені алу
    top_5_establishments = sorted_establishments[:5]

    if not top_5_establishments:
        update.message.reply_text("Өкінішке орай, жақын жерден халал мекемелер табылмады.")
        return

    response_message = "📍 **Сізге ең жақын 5 халал мекеме:**\n\n"
    
    for org in top_5_establishments:
        distance_str = f"{org['distance'] * 1000:.0f} м" if org['distance'] < 1 else f"{org['distance']:.1f} км"
        
        # Сертификаттың жарамдылық мерзімін алу (форматы әртүрлі болуы мүмкін, соған дайындалу керек)
        sert_date = org.get('sert_date', 'Белгісіз') # Мысал үшін, егер жоқ болса
        
        # Мекенжайды алу
        address = "Мекенжайы көрсетілмеген"
        if org.get('maplink') and len(org['maplink']) > 0 and 'address' in org['maplink'][0]:
            address = org['maplink'][0]['address']

        # 2GIS сілтемесін алу
        gis_link = ""
        if org.get('maplink') and len(org['maplink']) > 0 and 'link' in org['maplink'][0]:
            gis_link = f"➡️ 2GIS-те ашу ({org['maplink'][0]['link']})"

        response_message += (
            f"🏢 **{org.get('title', 'Аты жоқ')}**\n"
            f"ℹ️ Санаты: {org.get('category', {}).get('title', 'Белгісіз')}\n"
            f"🗺️ Мекенжайы: {address}\n"
            f"📏 Қашықтығы: {distance_str}\n"
            f"✅ Сертификат жарамды ({sert_date})\n"
            # f"📄 Сертификатты көру\n"  # Бұған сілтеме JSON-да жоқ, қажет болса қосымша дерек керек
            f"{gis_link}\n\n"
        )

    # Markdown форматында жіберу үшін parse_mode параметрін қолданамыз
    update.message.reply_text(response_message, parse_mode='Markdown')


# Бұл хэндлерді негізгі файлда тіркеу керек:
# dispatcher.add_handler(MessageHandler(Filters.location, location_handler))