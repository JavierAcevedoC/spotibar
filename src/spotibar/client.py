import argparse
import os
import pylast
import spotipy

from .config_helper import SpotibarConfig
from datetime import datetime
from .popups import ConfigPopup


class SpotibarClient():

    def __init__(self):
        '''
        TODO: Add args/kwargs here.
        '''
        self.scope = "playlist-read-private playlist-modify-private user-read-playback-state user-modify-playback-state playlist-modify-public"
        self.config = SpotibarConfig()

        self.client_id = self.config.get('client_id', None)
        self.client_secret = self.config.get('client_secret', None)
        self.currently_playing_trunclen = int(
            self.config.get('currently_playing_trunclen', 45)
        )

        self.redirect_uri = "http://127.0.0.1"
        self.cache_dir = os.path.expanduser("~") + "/.spotibar_cache"

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.cache_file = "auth_cache"

        self.client = self.get_client()

        self.lastfm_client = self.get_lastfm_client()

    def get_client(self):
        '''
        Returns the spotipy client ready for use.

        TODO: Add links to permissions explanations here?
        Example: https://developer.spotify.com/documentation/general/guides/scopes/#playlist-modify-private
        '''
        return spotipy.Spotify(
            auth_manager=spotipy.oauth2.SpotifyOAuth(
                scope=self.scope,
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                cache_path=f"{self.cache_dir}/{self.cache_file}"
            )
        )

    def get_lastfm_client(self):
        if self.config.get('should_heart_on_lastfm', False):
            try:
                return pylast.LastFMNetwork(
                    api_key=self.config.get('lastfm_api_key', None),
                    api_secret=self.config.get('lastfm_api_secret', None),
                    username=self.config.get('lastfm_username', None),
                    password_hash=self.config.get('lastfm_password_hash', None),
                )
            except Exception as e:
                print("Please configure ~/.spotibar_config.json with last.fm details.")
                print(e)

    def auth(self):
        '''
        Calls a method that requires authentication to ensure spotibar has
        sorted out its permissions from Spotify.
        '''
        self.is_currently_playing()
        print("Successfully authenticated.")

    def get_user_id(self):
        return self.client.me()['id']

    def get_current_device_id(self):
        # Get devices (needed if Spotify is paused for a period of time)
        # Lets just presume we're using the first one:

        devices = self.client.devices()
        return devices['devices'][0]['id']

    def is_currently_playing(self):
        '''
        Returns True if there is a currently playing song, False otherwise.
        '''
        try:
            return self.client.currently_playing()['is_playing']
        except Exception:
            return False

    def play(self):
        if not self.is_currently_playing():
            self.client.start_playback(device_id=self.get_current_device_id())

    def pause(self):
        if self.is_currently_playing():
            self.client.pause_playback(device_id=self.get_current_device_id())

    def toggle_playback(self):
        '''
        Plays the current track if currently paused. Pauses current track if
        currently playing.
        '''
        if self.is_currently_playing():
            self.pause()
        else:
            self.play()

    def previous(self):
        '''
        Goes to the previous playing song.
        '''
        try:
            self.client.previous_track(device_id=self.get_current_device_id())
        except Exception:
            print("TODO: HANDLE ERRORS!")

    def next(self):
        '''
        Goes to the next playing song.
        '''
        try:
            self.client.next_track(device_id=self.get_current_device_id())
        except Exception:
            print("TODO: HANDLE ERRORS!")

    def get_currently_playing_string(self):
        '''
        Returns the string ready for polybar
        '''
        try:
            current_track_name = self.client.currently_playing()['item']['name']
            current_artist_name = ', '.join(
                [
                    artist['name']
                    for artist in self.client.currently_playing()['item']['artists']
                ]
            )

            current_string = f"{current_track_name} by {current_artist_name}"

            if len(current_string) > self.currently_playing_trunclen:
                return current_string[:self.currently_playing_trunclen - 3] \
                    + "..."
            else:
                return current_string
        except Exception:
            return ""

    def get_current_track_id(self):
        return self.client.currently_playing()['item']['id']

    def get_user_playlists(self):
        '''
        Returns a list of dicts representing all the users playlists.

        TODO: Support more than 50 playlists.

        :rtype: list
        :returns: [
          {
            'name': <string playlist name>,
            'id': <string playlist ID>
          }, ..
        ]
        '''
        return [
            {
                'name': playlist['name'],
                'id': playlist['id']
            }
            for playlist in self.client.user_playlists(
                user=self.get_user_id()
            )['items']
        ]

    def create_playlist(self, name, public=False):
        '''
        Creates a playlist given a playlist name.

        :kwarg public: If True, the playlist will be public by default, else
        Private.
        '''
        self.client.user_playlist_create(self.get_user_id(), name, public=public)

    def get_monthly_playlist_id(self, name_format="%m ¦¦ %y", create_if_empty=True):
        '''
        Returns the ID of the monthly playlist as described by the name format
        which uses strftime strings.

        :kwarg create_if_empty: If True, creates the playlist if it doesn't exist
        and return that ID.
        '''
        playlists = self.get_user_playlists()

        playlist_id = [
            playlist['id'] for playlist in playlists
            if playlist['name'] == datetime.now().strftime(name_format)
        ]

        if len(playlist_id) == 0 and create_if_empty:
            self.create_playlist(datetime.now().strftime(name_format))
            return self.get_monthly_playlist_id(
                name_format=name_format,
                create_if_empty=create_if_empty
            )
        elif len(playlist_id) == 1:
            return playlist_id[0]
        else:
            print("TODO: ERROR HANDLING! SHOULDN'T BE POSSIBLE.")
            return playlist_id[0]

    def add_current_track_to_monthly_playlist(self):
        if self.config.get('should_put_to_monthly_playlist', True):
            self.client.playlist_add_items(
                self.get_monthly_playlist_id(),
                [self.get_current_track_id()]
            )

        if self.config.get('should_heart_on_lastfm', False):
            try:
                currently_playing = self.get_currently_playing_string()

                # TODO: Hacky. Works as long as the artist doesn't use the word
                # ' by '
                artist = currently_playing.split(' by ')[-1]
                track = ' '.join(currently_playing.split(' by ')[:-1])

                self.lastfm_client.get_track(artist, track).love()
            except Exception as e:
                print("Hearting track on lastfm failed.")
                print(e)


def main():
    spotibar_client = SpotibarClient()

    parser = argparse.ArgumentParser(
        description='Entrypoint for Spotify/Polybar integration.'
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--get-currently-playing", action="store_true")
    group.add_argument("--previous-track", action="store_true")
    group.add_argument("--next-track", action="store_true")
    group.add_argument("--toggle-playback", action="store_true")
    group.add_argument("--add-track-to-monthly-playlist", action="store_true")
    group.add_argument("--auth", action="store_true")
    group.add_argument("--config-popup", action="store_true")

    args = parser.parse_args()

    if args.get_currently_playing:
        print(spotibar_client.get_currently_playing_string())
    elif args.previous_track:
        spotibar_client.previous()
    elif args.next_track:
        spotibar_client.next()
    elif args.toggle_playback:
        spotibar_client.toggle_playback()
    elif args.add_track_to_monthly_playlist:
        spotibar_client.add_current_track_to_monthly_playlist()
    elif args.auth:
        spotibar_client.auth()
    elif args.config_popup:
        ConfigPopup()


if __name__ == '__main__':
    main()