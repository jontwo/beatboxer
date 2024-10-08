import re
from os import path, makedirs

from pydub import AudioSegment
from pydub.playback import play

from .default_oneshots import ONESHOT_PATH


class BeatBoxer:
    oneshots = {
        'hihat': AudioSegment.from_wav(path.join(ONESHOT_PATH, 'hihat.wav')),
        'kick': AudioSegment.from_wav(path.join(ONESHOT_PATH, 'kick.wav')),
        'snare': AudioSegment.from_wav(path.join(ONESHOT_PATH, 'snare.wav')),
        'clap': AudioSegment.from_wav(path.join(ONESHOT_PATH, 'clap.wav')),
        'crash': AudioSegment.from_wav(path.join(ONESHOT_PATH, 'crash.wav')),
        'bass': AudioSegment.from_wav(path.join(ONESHOT_PATH, 'bass.wav'))
    }

    def __init__(self, bpm=130, base_note=4, save_path=None):
        """
        Can be used to create and save a beat created by oneshots imported and
        saved in self.oneshots.

        Parameters:
        bpm - (default 130) The beats per minute to use
        base_note - (default 4) Which note to consider as one beat. It's the
                    lower of the two number in a time signature. Must be a
                    multiple of 4 cause ain't none of that weird stuff...
        save_path - (default None) The path to the directory to save to
        """
        # Checks if power of two or is zero
        if bool(base_note & (base_note - 1)) or not base_note:
            raise Exception("base_note can't be {}. ".format(base_note) +
                'It must be a power of 2.')

        self.bpm = bpm
        self.base_note = base_note
        self.save_path = save_path

        # The internal BPM, takes into account the value of `base_note`
        self._bpm = (self.base_note//4) * self.bpm
        self._spb = 60000//self._bpm
        self.current_beat = None
        self.stored_beats = {}

    def __str__(self):
        output = ''
        # Print out info of what is saved in current beat
        if self.current_beat is not None:
            output += '---------Current Beat--------\n'
            template = 'BPM: {} --- Time Signature: {} --- Number of Measures: {} --- Length: {} s'
            output += template.format(self.current_beat['bpm'],
                '{}/{}'.format(self.current_beat['beats_per_measure'],
                               self.current_beat['base_note']),
                self.current_beat['num_measures'],
                round(self.current_beat['audio'].duration_seconds, 3))
            output += '\n\n'

        # Print out info of what is saved in the stored beats
        if self.stored_beats:
            # How much space to allocate for each thing to print out
            template_lengths = [
                max(map(len, self.stored_beats.keys())),
                len(str(max([v['bpm'] for v in self.stored_beats.values()]))),
                len(str(max([v['beats_per_measure'] for v in self.stored_beats.values()]))) +
                len(str(max([v['base_note'] for v in self.stored_beats.values()]))) + 1,
                len(str(max([v['num_measures'] for v in self.stored_beats.values()]))),
                len(str(max([round(v['audio'].duration_seconds, 3) for v in self.stored_beats.values()])))
            ]

            output += '---------Stored Beats--------\n'        
            template = 'Name: {5:<{0}} --- BPM: {6:>{1}} --- Time Signature: {7:>{2}} --- ' + \
                    'Number of Measures: {8:>{3}} --- Length: {9:>{4}.3f} s'
            for name, data in self.stored_beats.items():
                output += template.format(*template_lengths, name, data['bpm'],
                    '{}/{}'.format(data['beats_per_measure'], data['base_note']),
                    data['num_measures'], data['audio'].duration_seconds) + '\n'
        return output

    def add_oneshot(self, oneshot_path, name=None):
        """
        Add one's own audio to the dictionary of oneshots.

        Paramters:
        oneshot_path - Path to the audio file
        name - (default None) What to name the audio file in self.oneshots. By
               default, it will be the file name
        """
        ftype = oneshot_path[-3:]
        name = name or oneshot_path.split(path.sep)[-1][:-4]
        self.oneshots[name] = AudioSegment.from_file(oneshot_path, ftype)

    def change_bpm(self, new_bpm):
        """
        Changes the bpm to `new_bpm`.
        """
        if new_bpm is not None:
            self.bpm = new_bpm
            self._bpm = (self.base_note//4) * self.bpm
            self._spb = 60000//self._bpm

    def change_base_note(self, new_base_note):
        """
        Changes the base note to `new_base_note`.
        """
        if new_base_note is not None:
            if bool(new_base_note & (new_base_note - 1)) or not new_base_note:
                raise Exception("base_note can't be {}. ".format(new_base_note) +
                    'It must be a power of 2.')

            self.base_note = new_base_note
            self._bpm = (self.base_note//4) * self.bpm
            self._spb = 60000//self._bpm

    @staticmethod
    def empty(num_beats=16):
        """
        Creates a template for an empty beat.

        Parameters:
        num_beats - (default 16) Number of beats for the template
        """
        return [Mlist() for _ in range(num_beats)]

    def _max_len(self, oneshots):
        """
        From the list of oneshots, returns the length of the longest one
        """
        if oneshots:
            return max(map(lambda x: len(self.oneshots[x]), oneshots))
        return 0

    def make_a_beat(self, measure, num_measures=9, repeatable=True,
                    _no_add=False, **shortcuts):
        """
        Creates a beat from the list `measure`. This method works by creating
        a silent 'canvas' of the appropriate length. Then, as it iterates
        through the `measure` list, it will create an overlay of every oneshot
        to be played (with silent buffers for the shorter oneshots) and this
        overlay is overlayed the 'canvas' at the appropriate place with the
        appropriate silent buffer to it. This way, oneshots of any length can
        be used.

        Parameters:
        measure - A list where each element gives the info on what oneshots
                  should be played on that beat. Each element is a list of
                  these oneshots
        num_measures - (default 9) The number of times that the given measure
                       should repeat
        repeatable - (default True) If True, does not add a buffer of silence
                     at the end of the beat for the last note to play, so it
                     can be repeated.
        _no_add - (default False) If True, will not add anything from shortcuts
        Shortcuts - Different shortcuts that can be used. Examples of them:

                    'every_beat': ['hihat', 'kick']
                (will play a hihat and snare on every beat)
                    'every_<nth>: [('kick', 1), ('snare', 2)]
                (will play a kick on every nth beat starting on the 2nd beat
                 and a snare every nth beat starting on the 3rd beat)
                    'single': {'hihat': [1, 2, 3], 'snare': [5, 9]}
                (will add a hihat on the 1st, 2nd and 3rd beat and a snare on
                 the 5th and 9th beat)
        """
            ## Here's a list of what each variable is ##
        ### Cause I KNOW I will forget... I'm not THAT naive ###
        # beat - the output (used colloquially rather than musically)
        # beat_length - the length of the entire beat
        # beat_measure - an element of the measure list
        # beat_sound - an element of a beat (since there can be multiple sounds
        #              per beat)
        # combined_beat_sounds - an audio of all the sounds we want overlayed
        #                        for the current beat
        # ind_beat - which beat we are on
        # ind_measure - which measure we are on
        # max_len - length of longest oneshot of beat_measure
        # measure - list of what each beat in the measure should play
        # measure_length - the time length of one measure
        # num_measures - how many times to repeat the measure
        # offset - The time offset at which the current beat should start
        # sound - the actuall AudioSegment object of beat_sound
            ##                  End                      ##
        if not _no_add:
            # Make the additions to the template
            measure = self._edit_template([Mlist(x) for x in measure], **shortcuts)

        # Total length of final audio file
        measure_length = self._spb * len(measure)
        beat_length = measure_length * num_measures
        beat = AudioSegment.silent(beat_length)
        if not repeatable:
            beat += AudioSegment.silent(self._max_len(measure[-1]))

        # Repeat for `num_measures` measures
        for ind_measure in range(num_measures):
            # Run through each beat of the measure
            for ind_beat, beat_measure in enumerate(measure):
                # If not to play anything on this `beat_measure`
                if not beat_measure:
                    continue
                # Find longest oneshot, so to add silence to shorter oneshots
                max_len = self._max_len(beat_measure)

                # Time at which this beat starts
                offset = ind_measure * measure_length + ind_beat * self._spb

                combined_beat_sounds = AudioSegment.silent(max_len)
                for beat_sound in beat_measure:
                    sound = self.oneshots[beat_sound]

                    # Overlay each sound, with silent padding if necessary
                    combined_beat_sounds = combined_beat_sounds.overlay(
                        sound + AudioSegment.silent(max_len - len(sound)))

                # Add beat at its offset with a silent padding
                beat = beat.overlay(combined_beat_sounds +
                    AudioSegment.silent(beat_length - max_len - offset),
                    position=offset)

        self.current_beat = {
            'audio': beat, 'beats_per_measure': len(measure), 'bpm': self.bpm,
            'num_measures': num_measures, 'base_note': self.base_note,
            'measure': list(measure), 'repeatable': repeatable}

    def play_beat(self, beat=None):
        """
        Plays the beat.

        Parameters:
        beat - (default self.current_beat) The beat to play
        """
        beat = beat or self.current_beat
        play(beat['audio'])

    def save_beat(self, name, beat=None, ftype='wav', save_path=None):
        """
        Saves self.current_beat as a .wav file.

        Parameters:
        name - Name of the file
        beat - (default self.current_beat) The beat to save
        ftype - (default 'wav') File type to save audio as
        save_path - (default self.save_path) Path to save directory
        """
        save_path = save_path or self.save_path
        if save_path is None:
            raise Exception('Please specify a path to a directory to save ' + \
                'with the argument `save_path` or specify a default path ' + \
                'with defining self.save_path.')

        if not path.exists(save_path):
            makedirs(save_path)

        beat = beat or self.current_beat
        beat['audio'].export(path.join(save_path, name + '.' + ftype), format=ftype)

    def store_beat(self, name):
        """
        Stores self.current_beat in the dict self.stored_beats.

        Parameters:
        name - Name of the beat
        """
        self.stored_beats[name] = self.current_beat

    def switch_current_beat(self, name, force=False):
        """
        Switches the beat stored in self.current_beat to one in 
        self.stored_beats.

        Parameters:
        name - Name of the beat
        force - (default False) If True and there is already a beat in
                self.current_beats, it will override it. If False, it will
                throw an error
        """
        if self.current_beat and not force:
            raise Exception('Audio already exists in self.current_beat. Use' + \
                ' force=True to override.')
        self.current_beat = self.stored_beats[name]

    def edit_current_beat(self, bpm=None, base_note=None, num_measures=None,
                          repeatable=None, remove={}, add={}):
        """
        Change BPM, base note and add and remove notes from the current beat.

        Parameters:
        bpm - (default None) The new BPM to change the beat to. If it is not
              specified, it will stay as the current BPM
        base-note - (default None) The new base note to change the beat to. If
                    it is not specified, it will stay as the current base note
        num_measures - (default None) How many measures. If not specified, it
                       will keep the number of measures the original had
        remove - (default {}) A dictionary of notes to remove. The syntax
                 follows exactly from **shortcuts from self.make_a_beat
        add - (default {}) Same as `remove` but adds notes. Again the syntax
              follows exactly from **shortcuts from self.make_a_beat
        """
        # Save current BPM and change to specified one
        old_bpm = self.bpm
        self.change_bpm(bpm)

        # Save current base_note and change to specified one
        old_base_note = self.base_note
        self.change_base_note(base_note)

        # Get the template
        measure = self.current_beat['measure']

        self._edit_template(measure, **add)
        self._edit_template(measure, 'remove', **remove)
        self.make_a_beat(measure, num_measures or self.current_beat['num_measures'],
            repeatable or self.current_beat['repeatable'], True)

        # Return the old BPM and base_note
        self.change_bpm(old_bpm)
        self.change_base_note(old_base_note)

    def _edit_template(self, measure, etype='append', **shortcuts):
        """
        Add or remove notes according to the shortcuts to measure.
        """
        if etype not in ['append', 'remove']:
            raise Exception('Unknown edit type: {}.'.format(etype))

        # Go through the kwargs
        for shortcut in shortcuts:
            # Edits oneshots for every beat
            if shortcut == 'every_beat':
                for ind_beat in range(len(measure)):
                    for oneshot in shortcuts[shortcut]:
                        measure[ind_beat].cchange(oneshot, etype)
            # Edits oneshots on every nth beat
            elif re.findall('every_(\d+)(?:st|nd|rd|th)', shortcut):
                nth = int(re.findall('every_(\d+)(?:st|nd|rd|th)', shortcut)[0])
                for ind_beat in range(len(measure)):
                    for oneshot in shortcuts[shortcut]:
                        # An offset of m will start on the (m+1)th beat and be
                        # repeated every nth beat
                        if ind_beat >= oneshot[1] and not (ind_beat - oneshot[1]) % nth:
                            measure[ind_beat].cchange(oneshot[0], etype)
            # Edits oneshots on specific beats
            elif shortcut == 'single':
                for oneshot, ind_beats in shortcuts['single'].items():
                    for ind_beat in ind_beats:
                        measure[ind_beat].cchange(oneshot, etype)

        return measure


class Mlist(list):
    """
    A list subclass to add some useful methods.
    """
    def cchange(self, n, etype):
        """
        Cappend and Cremove wrapped in one function.
        """
        if etype == 'append':
            self._cappend(n)
        elif etype == 'remove':
            self._cremove(n)

    def _cappend(self, n):
        """
        Careful/Conditional append. Only append if `n` is not in the list.
        """
        if n not in self:
            self.append(n)

    def _cremove(self, n):
        """
        Careful/Conditional remove. Don't throw error if `n` not in list.
        """
        if n in self:
            self.remove(n)


def main():
    # Create directory to save audio into
    from inspect import getsourcefile
    save = path.join(path.dirname(path.abspath(getsourcefile(lambda: 0))), 'outputs')

    # Create object with 120 beats per minute and quarter note as one beat
    b = BeatBoxer(bpm=120, base_note=4, save_path=save)

    # Create audio with 16 beats off an empty template for one measure:
    #     1) Every beat play a hihat
    #     2) Every 4th beat starting on the 2nd beat plays a snare
    #     3) Every 3rd beat starting on the 2nd beat plays a snare
    #     4) Every 8th beat starting on the 1st beat plays a crash
    # Time signature will be 16/4
    b.make_a_beat(b.empty(), num_measures=1, every_beat=['hihat'],
        every_4th=[('snare', 1)], every_3rd=[('kick', 1)], every_8th=[('crash', 0)])
    b.store_beat('dope1')

    # Change to having an eight note as one beat
    b.change_base_note(8)
    # Create same thing as before but it will now be twice as fast with a 
    # time signature of 16/8 and played for 4 measures
    b.make_a_beat(b.empty(), num_measures=4, every_beat=['hihat'],
        every_4th=[('snare', 1)], every_3rd=[('kick', 1)], every_8th=[('crash', 0)])
    b.store_beat('dope2')

    # Change to 100 beats per minute
    b.change_bpm(100)
    # Now have a time signature of 3/8 for 12 measures
    b.make_a_beat(b.empty(3), num_measures=12, every_beat=['hihat'],
        every_3rd=[('snare', 2), ('kick', 1)])
    b.store_beat('lastly dope')

    # Save one of the beats
    b.save_beat('dopest', b.stored_beats['dope2'])

    # Printing the object will display the stored and current beat(s)
    print(b)

    # Second one is great but I don't like the first one, let's edit it...
    b.switch_current_beat('dope1', force=True)
    # Remove every snare and every 2nd hihat. Then add a bass on every kick and
    # re-add the snare on every 4th note but with a 2 beat offset.
    b.edit_current_beat(bpm=140, base_note=8, num_measures=4, remove={
        'every_beat': ['snare'], 'every_2nd': [('hihat', 1)]
    }, add={
        'every_3rd': [('bass', 1)], 'every_4th': [('snare', 2)]
    })
    # Now, there is still the original 'dope1' beat in b.stored_beats. We can
    # either overwrite it with this or store as a new one like so:
    b.store_beat('way better than dope1')
    # And lets save that bad boy
    b.save_beat('dopestest')

    print('\n\nDid some editting...')
    print(b)

if __name__ == "__main__":
    main()
