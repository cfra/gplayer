#!/usr/bin/python

import os
import sys
import thread
import threading
import time

import glib
import gobject
import pygst
pygst.require("0.10")
import gst

class Player:
	def __init__(self):
		self.finished = threading.Event()
		self.player = gst.element_factory_make("playbin2", "player")

		self.imagesink = gst.element_factory_make("autovideosink", "imagesink")
		self.imagesink.get_pad("sink").add_event_probe(self.on_sink_event)
		self.player.set_property("video-sink", self.imagesink)

		self.bus = self.player.get_bus()
		self.bus.add_signal_watch()
		self.bus.enable_sync_message_emission()
		self.bus.connect("message", self.on_message)
		self.bus.connect("sync-message::element", self.on_sync_message)

	def seek(self, off):
		pos_int = self.player.query_position(gst.FORMAT_TIME, None)[0]
		seek_ns = int(pos_int + (off * 1000000000))
		if seek_ns < 0:
			seek_ns = 0
		self.player.seek_simple(gst.FORMAT_TIME, gst.SEEK_FLAG_FLUSH, seek_ns)

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

		if key in seek_keys:
			self.seek(seek_keys[key])
			return False
		elif key == 'q':
			loop.quit()
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

	def on_sink_event(self, imagesink, event):
		structure = event.get_structure()
		if structure is None:
#			print >>sys.stderr, "Unknown event: %r" % event
			return True

		struct_name = structure.get_name()
		if struct_name == 'application/x-gst-navigation':
			return self.on_navigation_event(structure)
#		else:
#			print >>sys.stderr, "Event with unknown structure %s" % structure.to_string()
		return True

	def on_have_xwindow_id(self, imagesink):
		try:
			imagesink.set_property('force-aspect-ratio', True)
		except Exception, e:
			print 'Error forcing aspect ratio: %s' % e

	def on_sync_message(self, bus, message):
#		print >>sys.stderr, 'sync-message'
		if message.structure is None:
			return
		message_name = message.structure.get_name()
		if message_name == 'have-xwindow-id':
			return self.on_have_xwindow_id(message.src)
#		print >>sys.stderr, 'message_name: %s' % message_name

	def start(self):
		for f in sys.argv[1:]:
			self.finished.clear()
			if os.path.isfile(f):
				self.player.set_property("uri",
					"file://%s" % os.path.abspath(f))
			else:
				self.player.set_property("uri", f)
			sys.stderr.write("\nPlaying %s\n" % f)
			self.player.set_state(gst.STATE_PLAYING)
			while not self.finished.wait(0.1):
				if self.finished.is_set():
					break
				try:
					pos = self.player.query_position(gst.FORMAT_TIME, None)
				except gst.QueryError:
					sys.stdout.write("\r?.?? / ?.??")
				else:
					sys.stdout.write("\r%d.%02d / %d.%02d" % (
						pos[0] / 1000000000,
						(pos[0] / 10000000) % 100,
						pos[1] / 1000000000,
						(pos[1] / 10000000) % 100))
				sys.stdout.flush()
		loop.quit()

	def on_message(self, bus, message):
#		print >>sys.stderr, 'bus-message'
		if message.structure is not None:
			message_name = message.structure.get_name()
#			print >>sys.stderr, 'message_name: %s' % message_name
		t = message.type
		if t not in [gst.MESSAGE_EOS, gst.MESSAGE_ERROR]:
			return
		if t == gst.MESSAGE_ERROR:
			err,debug = message.parse_error()
			print "Error: %s" % err, debug
		self.player.set_state(gst.STATE_NULL)
		self.finished.set()

mainclass = Player()
thread.start_new_thread(mainclass.start, ())
gobject.threads_init()
loop = glib.MainLoop()
loop.run()
				
