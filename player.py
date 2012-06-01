#!/usr/bin/python

import argparse
import os
import sys

import glib
import gobject
import pygst
pygst.require("0.10")
import gst

class Player(object):
    def __init__(self, imagesink=None, medium=[]):
        """Store the settings and register the real setup function in event loop"""
        self.settings = {}
        self.settings['imagesink'] = imagesink
        self.settings['medium'] = medium

        # We will only start the player, once the event loop is running
        glib.idle_add(self.setup)

    def setup_gstreamer(self):
        """Create the actual gstreamer setup (it is probably quite crappy,
           I was unable to find any real documentation or best-practices list
           for it, all I had was some tutorials (thanks guys), a few pointers
           from #gstreamer at FreeNode (thanks too)"""
        self.player = gst.element_factory_make("playbin2", "player")

        if self.settings['imagesink'] is None:
            self.imagesink = gst.element_factory_make("autovideosink", "imagesink")
        else:
            self.imagesink = gst.element_factory_make(self.settings['imagesink'], "imagesink")

        self.imagesink.get_pad("sink").add_event_probe(self.on_sink_event)
        self.player.set_property("video-sink", self.imagesink)

        self.volume = gst.element_factory_make("volume", "volume")
        self.audiosink = gst.element_factory_make("autoaudiosink", "audiosink")
        self.audioout = gst.Bin()
        self.audioout.add(self.volume, self.audiosink)
        gst.element_link_many(self.volume, self.audiosink)
        self.audioout.add_pad(gst.GhostPad("sink", self.volume.get_pad("sink")))
        self.player.set_property("audio-sink", self.audioout)

        self.bus = self.player.get_bus()
        self.bus.add_signal_watch()
        self.bus.enable_sync_message_emission()
        self.bus.connect("message", self.on_message)
        self.bus.connect("sync-message::element", self.on_sync_message)

    def setup_playlist(self):
        """Build a list from all the urls given to our constructor"""
        self.playlist_pos = 0
        self.playlist = []
        for f in self.settings['medium']:
            if os.path.isfile(f):
                self.playlist.append("file://%s" % os.path.abspath(f))
            else:
                self.playlist.append(f)

        # Call process_playlist to load first medium and set correct state
        self.process_playlist()

    def setup(self):
        """This function does the actual initialization"""
        super(Player, self).__init__()

        self.setup_gstreamer()
        self.setup_playlist()

        # Return false means that this is not rescheduled
        return False

    def seek(self, off):
        pos_int = self.player.query_position(gst.FORMAT_TIME, None)[0]
        seek_ns = int(pos_int + (off * 1000000000))
        if seek_ns < 0:
            seek_ns = 0
        self.player.seek_simple(gst.FORMAT_TIME, gst.SEEK_FLAG_FLUSH, seek_ns)

    def change_volume(self, fact):
        v = self.volume.get_property("volume")
        v *= fact
        # More than 500% Volume is usally not a good idea
        if v > 5:
            v = 5
        self.volume.set_property("volume", v)

    def toggle_mute(self):
        self.volume.set_property("mute", not self.volume.get_property("mute"))

    def quit(self):
        # User requested shutdown
        # Clear the playlist
        self.playlist = []

        # Post an End-Of-Stream so the pipeline gets destroyed
        self.bus.post(gst.message_new_eos(self.bus))

    def switch(self, what):
        maximum = self.player.get_property("n-%s" % what)
        if maximum <= 0:
            return # There aren't multiple whats, so we can't switch anything

        # The tracks count from zero. This implements cycling through all tracks
        current = self.player.get_property("current-%s" % what)
        current += 1
        if current >= maximum:
            current = 0

        # Actually set the new track
        self.player.set_property("current-%s" % what, current)

    def un_pause(self):
        state = self.player.get_state()[1]
        if state == gst.STATE_PAUSED:
            self.player.set_state(gst.STATE_PLAYING)
        else:
            self.player.set_state(gst.STATE_PAUSED)
    
    def on_key_press(self, key):
        #print 'Key pressed: %s' % structure.to_string()
        return True

    def on_key_release(self, key):
        seek_keys = {
            u'Left': -10,
            u'Right': 10,
            u'Down': -60,
            u'Up': 60,
            u'Next': -600,
            u'Prior': 600
        }

        volume_keys = {
            u'9':  0.9,
            u'0':  1.2
        }

        switch_keys = {
            u'a': 'audio',
            u'j': 'text',
        }

        if key in seek_keys:
            self.seek(seek_keys[key])
            return False
        elif key == u'space':
            self.un_pause()
            return False
        elif key in volume_keys:
            self.change_volume(volume_keys[key])
            return False
        elif key == u'm':
            self.toggle_mute()
            return False
        elif key in switch_keys:
            self.switch(switch_keys[key])
            return False
        elif key == u'q':
            self.quit()
            return False
        print >>sys.stderr, 'Key released: %s' % key
        return True

    def on_navigation_event(self, structure):
        event = structure['event']
        if event == 'key-press':
            return self.on_key_press(structure['key'])
        elif event == 'key-release':
            return self.on_key_release(structure['key'])
        # elif mouse-move
        # elif mouse-button-press
        # elif mouse-button-release
        return True

    def on_sink_event(self, unused_imagesink, event):
        structure = event.get_structure()
        if structure is None:
#            print >>sys.stderr, "Unknown event: %r" % event
            return True

        struct_name = structure.get_name()
        if struct_name == 'application/x-gst-navigation':
            return self.on_navigation_event(structure)
#        else:
#            print >>sys.stderr, "Event with unknown structure %s" % structure.to_string()
        return True

    def on_have_xwindow_id(self, imagesink):
        try:
            imagesink.set_property('force-aspect-ratio', True)
        except Exception, e:
            print 'Error forcing aspect ratio: %s' % e

    def on_sync_message(self, unused_bus, message):
#        print >>sys.stderr, 'sync-message'
        if message.structure is None:
            return
        message_name = message.structure.get_name()
        if message_name == 'have-xwindow-id':
            return self.on_have_xwindow_id(message.src)
#        print >>sys.stderr, 'message_name: %s' % message_name

    def process_playlist(self):
        if self.playlist_pos >= len(self.playlist):
            loop.quit()
            return False

        # Load next medium and advance index
        next_medium = self.playlist[self.playlist_pos]
        self.playlist_pos += 1

        self.player.set_property("uri", next_medium)
        self.player.set_state(gst.STATE_PLAYING)
        return True

    def on_message(self, unused_bus, message):
#        print >>sys.stderr, 'bus-message'
        if message.structure is not None:
            pass
#            message_name = message.structure.get_name()
#            print >>sys.stderr, 'message_name: %s' % message_name
        t = message.type
        if t not in [gst.MESSAGE_EOS, gst.MESSAGE_ERROR]:
            return
        if t == gst.MESSAGE_ERROR:
            err,debug = message.parse_error()
            print "Error: %s" % err, debug
        self.player.set_state(gst.STATE_NULL)
        self.process_playlist()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GStreamer based slick media player')
    parser.add_argument('-vo', dest='imagesink', help='Overwrite the default video output')
    parser.add_argument('medium', nargs='+', help='Media which should be played')
    options = parser.parse_args()

    gobject.threads_init()
    loop = glib.MainLoop()
    player = Player(**options.__dict__)

    try:
        loop.run()
    except KeyboardInterrupt:
        loop.quit()
# vim: expandtab:tabstop=4:shiftwidth=4
