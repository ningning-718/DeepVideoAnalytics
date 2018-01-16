import time
import shlex,json,os,zipfile,logging
import subprocess as sp
from PIL import Image
from ..models import Frame, Segment


class VideoDecoder(object):
    """
    Wrapper object for a video / dataset
    """

    def __init__(self,dvideo,media_dir):
        self.dvideo = dvideo
        self.primary_key = self.dvideo.pk
        self.media_dir = media_dir
        self.local_path = dvideo.path()
        self.segments_dir = "{}/{}/segments/".format(self.media_dir,self.primary_key)
        self.duration = None
        self.width = None
        self.height = None
        self.metadata = {}
        self.segment_frames_dict = {}
        self.csv_format = None

    def detect_csv_segment_format(self):
        format_path = "{}format.txt".format(self.segments_dir)
        self.csv_format = {}
        if not os.path.isfile(format_path):
            command ="ffprobe -i {}0.mp4 -show_frames -select_streams v:0 -print_format csv=nokey=0".format(self.segments_dir)
            csv_format_lines = sp.check_output(shlex.split(command))
            with open(format_path,'w') as formatfile:
                formatfile.write(csv_format_lines)
            logging.info("Generated csv format {}".format(self.csv_format))
        for line in file(format_path).read().splitlines():
            if line.strip():
                for i,kv in enumerate(line.strip().split(',')):
                    if '=' in kv:
                        k,v = kv.strip().split('=')
                        self.csv_format[k] = i
                    else:
                        self.csv_format[kv] = i
                break
        self.field_count = len(self.csv_format)
        self.pict_type_index = self.csv_format['pict_type']
        self.time_index = self.csv_format['best_effort_timestamp_time']

    def parse_segment_framelist(self,segment_id, framelist):
        if self.csv_format is None:
            self.detect_csv_segment_format()
        frames = {}
        findex = 0
        for line in framelist.splitlines():
            if line.strip():
                entries = line.strip().split(',')
                if len(entries) == self.field_count:
                    frames[findex] = {'type': entries[self.pict_type_index], 'ts': float(entries[self.time_index])}
                    findex += 1
                else:
                    errro_message = "format used {} \n {} (expected) != {} entries in {} \n {} ".format(self.csv_format,self.field_count,len(entries),segment_id, line)
                    logging.error(errro_message)
                    raise ValueError, errro_message
        return frames

    def get_metadata(self):
        command = ['ffprobe','-i',self.local_path,'-print_format','json','-show_format','-show_streams','-v','quiet']
        p = sp.Popen(command,stdout=sp.PIPE,stderr=sp.STDOUT,stdin=sp.PIPE)
        p.wait()
        output, _ = p.communicate()
        self.metadata = json.loads(output)
        try:
            self.duration = float(self.metadata['format']['duration'])
            self.width = float(self.metadata['streams'][0]['width'])
            self.height = float(self.metadata['streams'][0]['height'])
        except:
            raise ValueError,"{} : {}".format(self.local_path,str(output))
        self.dvideo.metadata = self.metadata
        self.dvideo.length_in_seconds = self.duration
        self.dvideo.height = self.height
        self.dvideo.width = self.width
        self.dvideo.save()

    def decode_segment(self,ds,denominator,event_id=None):
        output_dir = "{}/{}/{}/".format(self.media_dir, self.primary_key, 'frames')
        input_segment = ds.path()
        ffmpeg_command = 'ffmpeg -fflags +igndts -loglevel panic -i {} -vf'.format(input_segment) # Alternative to igndts is setting vsync vfr
        df_list = []
        filter_command = '"select=not(mod(n\,{}))+eq(pict_type\,PICT_TYPE_I)" -vsync 0'.format(denominator)
        output_command = "{}/segment_{}_%d_b.jpg".format(output_dir,ds.segment_index)
        command = " ".join([ffmpeg_command,filter_command,output_command])
        logging.info(command)
        try:
            _ = sp.check_output(shlex.split(command), stderr=sp.STDOUT)
        except:
            raise ValueError,"for {} could not run {}".format(self.dvideo.name,command)
        with open(ds.framelist_path()) as framelist:
            segment_frames_dict = self.parse_segment_framelist(ds.segment_index, framelist.read())
        ordered_frames = sorted([(k,v) for k,v in segment_frames_dict.iteritems() if k%denominator == 0 or v['type'] == 'I'])
        frame_width, frame_height = 0, 0
        for i,f_id in enumerate(ordered_frames):
            frame_index, frame_data = f_id
            src = "{}/segment_{}_{}_b.jpg".format(output_dir,ds.segment_index,i+1)
            dst = "{}/{}.jpg".format(output_dir,frame_index+ds.start_index)
            try:
                os.rename(src,dst)
            except:
                raise ValueError,str((src, dst, frame_index, ds.start_index))
            if i ==0:
                im = Image.open(dst)
                frame_width, frame_height = im.size  # this remains constant for all frames
            df = Frame()
            df.frame_index = int(frame_index+ds.start_index)
            df.video_id = self.dvideo.pk
            df.keyframe = True if frame_data['type'] == 'I' else False
            df.t = frame_data['ts']
            df.segment_index = ds.segment_index
            df.h = frame_height
            df.event_id = event_id
            df.w = frame_width
            df_list.append(df)
        _ = Frame.objects.bulk_create(df_list, batch_size=1000)

    def segment_video(self,event_id):
        segments_dir = "{}/{}/{}/".format(self.media_dir, self.primary_key, 'segments')
        command = 'ffmpeg -loglevel panic -i {} -c copy -map 0 -segment_time 1 -f segment ' \
                  '-segment_list_type csv -segment_list {}/segments.csv ' \
                  '{}/%d.mp4'.format(self.local_path, segments_dir, segments_dir)
        logging.info(command)
        segmentor = sp.Popen(shlex.split(command))
        segmentor.wait()
        if segmentor.returncode != 0:
            raise ValueError
        else:
            timer_start = time.time()
            start_index = 0
            for line in file('{}/segments.csv'.format(segments_dir)):
                segment_file_name, start_time, end_time = line.strip().split(',')
                segment_id = int(segment_file_name.split('.')[0])
                command = 'ffprobe -select_streams v -show_streams  -print_format json {}  '.format(segment_file_name)
                # logging.info(command)
                segment_json = sp.check_output(shlex.split(command), cwd=segments_dir)
                command = 'ffprobe -show_frames -select_streams v:0 -print_format csv {}'.format(segment_file_name)
                # logging.info(command)
                framelist= sp.check_output(shlex.split(command), cwd=segments_dir)
                with open("{}/{}.txt".format(segments_dir,segment_file_name.split('.')[0]),'w') as framesout:
                    framesout.write(framelist)
                self.segment_frames_dict[segment_id] = self.parse_segment_framelist(segment_id,framelist)
                logging.warning("Processing line {}".format(line))
                start_time = float(start_time)
                end_time = float(end_time)
                ds = Segment()
                ds.segment_index = segment_id
                ds.start_time = start_time
                ds.start_index = start_index
                start_index += len(self.segment_frames_dict[segment_id])
                ds.frame_count = len(self.segment_frames_dict[segment_id])
                ds.end_time = end_time
                ds.video_id = self.dvideo.pk
                ds.event_id = event_id
                ds.metadata = segment_json
                ds.save()
            logging.info("Took {} seconds to process {} segments".format(time.time() - timer_start,len(self.segment_frames_dict)))
        self.dvideo.frames = sum([len(c) for c in self.segment_frames_dict.itervalues()])
        self.dvideo.segments = len(self.segment_frames_dict)
        self.dvideo.save()
        self.detect_csv_segment_format() # detect and save

