from flask import Flask, render_template, url_for, redirect, request, session
from oauth import *
from dataclient import *
from spotifyapiclient import *
from azureclient import *
import time

app = Flask(__name__)
app.secret_key = "YOUR SECRET KEY"

oauth_client = SpotifyOauthClient()

@app.route('/')
def index():

    auth_url = oauth_client.get_auth_url()
    return render_template("login.html", url=auth_url)

@app.route("/redirect/")
def redirectPage():

    auth_code = request.args.get('code')
    auth_info = oauth_client.get_token_info(auth_code)

    session['oauth_info'] = auth_info
    session['start_time'] = int(time.time())
    session['time_frame'] = "short_term"
    session['cols'] = ['Danceability', 'Energy', 'Acousticness', 'Speechiness', 'Valence', 'Instrumentalness']

    return redirect(url_for('profilePage', _external=True))

@app.route("/profile")
def profilePage():

    api_client = init_api_client()
    request_data = api_client.get_user_info()

    #user general info
    user_info = request_data["user_info"]
    username = user_info["display_name"]
    followers = user_info["followers"]["total"]
    profile_pic = user_info["images"][0]["url"] if len(user_info["images"]) != 0 else None

    #playlists user has
    playlist_info = request_data["playlist_info"]
    num_of_playlists = len(playlist_info['items']) 

    #how many people the user is following/followed by
    user_follow_info = request_data["following_info"]
    num_of_followed_artists = len(user_follow_info['artists']['items'])

    return render_template("profile.html", username=username, followers=followers, pic=profile_pic, playlists=num_of_playlists, follows=num_of_followed_artists)
    
@app.route("/music")
def myMusic():

    return configure_user_top('music.html', 10)

@app.route('/change-time/<string:id>')
def changeTime(id):
    
    if id[-1] == "M":
        session['time_frame'] = id[:-1]
        return redirect(url_for('more', _external=True))
    
    elif id[-1] == "A":
        session['time_frame'] = id[:-1]
        return redirect(url_for('analytics', _external=True))

    else:      
        session['time_frame'] = id
        return redirect(url_for('myMusic', _external=True))

@app.route('/info/<string:id>')
def info(id):

    api_client = init_api_client()

    if id[-1] == "T":

        info_type = "track" 
        track_id = id[:-1]

        try:
            track_info = api_client.get_track_or_artist_info(track_id, "tracks")
            audio_info = api_client.get_audio_features(track_id)
            lyrics_analyzer = AzureAnalyticsClient()

        except:
            return redirect(url_for('myMusic', _external=True))

        track_name = track_info['name']
        track_artist = track_info['artist']
        song_lyrics = api_client.get_song_lyrics(track_artist, track_name)

        if song_lyrics != "Lyrics not able to be analyzed":

            sentiment = lyrics_analyzer.sentiment_analysis(song_lyrics)
            song_overall_sentiment = sentiment['overall']
            song_positive_score = sentiment['positive']
            song_negative_score = sentiment['negative']
            song_neutral_score = sentiment['neutral']

            key_phrases = lyrics_analyzer.key_phrase_extraction(song_lyrics)

            for phrase in key_phrases:
                if phrase != "br":
                    song_lyrics = song_lyrics.replace(phrase, f"<span>{phrase}</span>")

            audio_features = audio_info['features']
            track_popularity = track_info['popularity']
            tempo = audio_info['tempo']
            loudness = audio_info['loudness']

            return render_template('info.html', t=tempo, l=loudness, id=track_id, p=track_popularity, labels=session.get('cols'), data=audio_features, type=info_type, lyrics=song_lyrics, overall=song_overall_sentiment, positive=song_positive_score, negative=song_negative_score, neutral=song_neutral_score, allowed=True)
        
        else:
            audio_features = audio_info['features']
            track_popularity = track_info['popularity']
            tempo = audio_info['tempo']
            loudness = audio_info['loudness']

            return render_template('info.html', t=tempo, l=loudness, id=track_id, p=track_popularity, labels=session.get('cols'), data=audio_features, type=info_type, allowed=False)

    else:
        artist_id = id[:-1]
        artist_info = api_client.get_track_or_artist_info(artist_id, "artists")
        info_type="artist"

        followers = f"{artist_info['followers']:,d}"
        genres = artist_info['genres']
        name = artist_info['name']
        image = artist_info['image']
        popularity = artist_info['popularity']

        return render_template('info.html', f=followers, g=genres, n=name, i=image, p=popularity, type=info_type)

@app.route('/more')
def more():

    return configure_user_top('more.html', 30)

@app.route("/analytics")
def analytics():

    api_client = init_api_client()
    user_top_songs = api_client.get_user_top_info(50, session.get('time_frame'), "tracks")
    user_top_artists = api_client.get_user_top_info(33, session.get('time_frame'), "artists")

    if not user_top_songs or not user_top_artists: #if the user has no data (i.e the returned dict is empty)
        return error_page("Sorry, your account does not seem to have any data I can analyze. Please go back to the 'My Music' section and try switching the timeframe to see if you have any data there!")

    else:
        song_ids = user_top_songs['id']
        artist_ids = user_top_artists['id']

    data_client = DataClient(api_client, song_ids, artist_ids, session.get('time_frame'))
    cols = session.get('cols')

    #popularity info
    track_popularity = data_client.get_user_avg_popularity("tracks")
    spotify_track_popularity = data_client.get_spotify_charts_avg_popularity()['track']
    artist_popularity = data_client.get_user_avg_popularity("artists")
    spotify_artist_popularity = data_client.get_spotify_charts_avg_popularity()['artist']

    popularity_graph_labels = ["Popularity of your Top Songs", "Popularity of Top Songs in 2020", "Popularity of your Top Artists", "Popularity of Top Artists in 2020"]
    popularity_data = [track_popularity, spotify_track_popularity, artist_popularity, spotify_artist_popularity] 
 
    #audio features info
    user_avg_features = data_client.get_user_top_avg_audio_features(cols)
    spotify_avg_features = data_client.get_spotify_charts_avg_features(cols)  #audio features info

    #genres
    user_top_genres = data_client.get_user_top_genres()

    #percentages
    audio_feature_similarities = data_client.get_similarity_between_features(user_avg_features, spotify_avg_features)
    track_popularity_similarities = data_client.get_similarity_between_features([track_popularity], [spotify_track_popularity])
    artist_popularity_similarities = data_client.get_similarity_between_features([artist_popularity], [spotify_artist_popularity])
    song_occurence = data_client.get_number_of_same_songs_percentage()

    basic_score = round(((audio_feature_similarities) + track_popularity_similarities + (artist_popularity_similarities) + song_occurence) / 4)
    
    return render_template('analytics.html', time=session.get("time_frame"), user_avg_features=user_avg_features, top_avg_features=spotify_avg_features, pop_labels=popularity_graph_labels, pop_data=popularity_data, genres=user_top_genres, score=basic_score, cols=cols, zip=zip)

@app.route("/new", methods=['POST', 'GET'])
def new():

    api_client = init_api_client()
    user_top_songs = api_client.get_user_top_info(50, session.get('time_frame'), "tracks")
    user_top_artists = api_client.get_user_top_info(33, session.get('time_frame'), "artists")

    if not user_top_songs or not user_top_artists: #if the user has no data (i.e the returned dict is empty)
        return error_page("Sorry, your account does not seem to have any data I can analyze. Please go back to the 'My Music' section and try switching the timeframe to see if you have any data there!")

    else:
        song_ids = user_top_songs['id']
        artist_ids = user_top_artists['id']

    data_client = DataClient(api_client, song_ids, artist_ids, session.get('time_frame'))
    cols = session.get('cols')

    #user info
    user_id = api_client.get_user_info()['user_info']['id']

    #tracks
    seeds = data_client.get_recommendation_seeds(len(user_top_songs['name']), len(user_top_artists['name']))
    user_audio_features = data_client.get_user_top_avg_audio_features(cols)
    user_popularity = data_client.get_user_avg_popularity("tracks")

    #tracks
    try:
        get_recommended_tracks_info = api_client.get_track_recommendations(10, seeds, user_audio_features, user_popularity, "normal")
    
    except:
        return error_page("Can't get recommendations.")

    track_names = get_recommended_tracks_info['name']
    track_ids = get_recommended_tracks_info['id']
    track_image = get_recommended_tracks_info['image']
    track_artists = get_recommended_tracks_info['trackartistname']
    track_albums = get_recommended_tracks_info['trackalbumname']

    #artists
    get_recommended_artists_info = api_client.get_artist_recommendations(seeds['artist'])
    artist_names = get_recommended_artists_info['name']
    artist_ids = get_recommended_artists_info['id']
    artist_images = get_recommended_artists_info['image']

    
    if request.method == "POST":
        
        user_inputed_popularity = int(request.form['pop'])
        user_inputed_audio_features = [[f"target_{col.lower()}", float(request.form[col])] for col in cols if float(request.form[col]) != 0.0]
        playlist_name = request.form['playlistname']

        try:
            more_tracks = api_client.get_track_recommendations(50, seeds, user_inputed_audio_features, user_inputed_popularity, "post")
        
        except:
            return error_page("Can't get recommendations.")

        new_names = more_tracks['name']
        new_ids = more_tracks['id']
        new_images = more_tracks['image']
        new_artists = more_tracks['trackartistname']
        new_albums = more_tracks['trackalbumname']

        get_new_playlist_id = api_client.create_new_playlist(user_id, playlist_name)['id']
        modified_ids = ["spotify:track:" + track_id for track_id in new_ids]
        csv_ids = ','.join(modified_ids)

        api_client.add_items_to_playlist(get_new_playlist_id, csv_ids)

    return render_template('recommendations.html', t_names=track_names, cols=cols, t_ids=track_ids, t_images=track_image, t_artists=track_artists, t_albums=track_albums, a_names=artist_names, a_ids=artist_ids, a_images=artist_images, zip=zip)

def init_api_client(): 
    
    oauth_info = session.get('oauth_info')
    oauth_info["expires_in"]=36000000
    start_time = session.get('start_time') #gets the time at which access_token was first given
    
    current_time = int(time.time()) #gets the time when this function is called
    token_expiry = oauth_info['expires_in']  #sets the token expiry time which is 3600 seconds or 1 hour
    time_diff = current_time - start_time #how much time has passed since token was given

    if time_diff > token_expiry: #if more than an hour has passed, a new access_token will be provided
        new_token = oauth_client.refresh_token(oauth_info['refresh_token'])   #logic for refreshing access token
        start_time = int(time.time())
        return SpotifyApiClient(new_token['access_token'])
    
    else:
        return SpotifyApiClient(oauth_info['access_token'])

def configure_user_top(html_page, limit):

    api_client = init_api_client()
    time_frame = session.get('time_frame')

    user_top_tracks = api_client.get_user_top_info(limit, time_frame, "tracks")
    user_top_artists = api_client.get_user_top_info(limit, time_frame, "artists")

    if not user_top_tracks: #if the returned data is empty it will set the values to empty
        songs = ['']
        song_ids = ['']
        song_covers = ['']
        song_artists = ['']
        song_albums = ['']
    
    else:
        songs = user_top_tracks['name']
        song_ids = user_top_tracks['id']
        song_covers = user_top_tracks['image']
        song_artists = user_top_tracks['trackartistname']
        song_albums = user_top_tracks['trackalbumname']

    if not user_top_artists:
        artists = ['']
        artist_ids = ['']
        artist_covers = ['']
    
    else:
        artists = user_top_artists['name']
        artist_ids = user_top_artists['id']
        artist_covers = user_top_artists['image']

    return render_template(html_page, songs=songs, song_ids=song_ids, song_covers=song_covers, song_artists=song_artists, song_albums=song_albums, artists=artists, artist_ids=artist_ids, artist_covers=artist_covers, zip=zip, time=time_frame)

def error_page(text):
    return render_template('error.html', text=text)

if __name__ == "__main__":
    app.run()