import re
from pathlib import Path

import anyio
import gradio as gr
from deep_translator import GoogleTranslator
from voicevox import Client, Style

from modules import shared

params: dict[str, None|bool|int|str] = {
    'activate': True,
    'selected_voice': None,
    'autoplay': False,
    'selected_style': None,
    'speaker_id': None,
    'interrogative_speak': True,
    'translate': True,
    'url': 'http://localhost:50021'
}

wav_idx = 0
speakers = {}
now_style: dict[str, Style] = {}


def remove_surrounded_chars(string):
    # this expression matches to 'as few symbols as possible (0 upwards) between any asterisks' OR
    # 'as few symbols as possible (0 upwards) between an asterisk and the end of the string'
    return re.sub("\*[^\*]*?(\*|$)", '', string)

def connect():
    global now_style, speakers
    async def tmp():
        temp = {}
        try:
            async with Client(params['url']) as client:
                for i in await client.fetch_speakers((await client.fetch_core_versions())[0]):
                    temp[i.name] = i
        except:
            pass
        return temp
    speakers = anyio.run(tmp)
    if len(speakers) != 0:
        params['selected_voice'] = [i for i in speakers.keys()][0]
        params['selected_style'] = speakers[params['selected_voice']].styles[0].name
        params['speaker_id'] = speakers[params['selected_voice']].styles[0].id
        now_style = {}
        for i in speakers[params['selected_voice']].styles:
            now_style[i.name] = i
        return gr.Dropdown.update(choices=[i for i in speakers.keys()], value=params['selected_voice']), gr.Dropdown.update(value=params['selected_style'], choices=[i for i in now_style.keys()]), gr.Checkbox.update(interactive=True)
    params['activate'] = False
    return gr.Dropdown.update(), gr.Dropdown.update(), gr.Checkbox.update(interactive=False)
connect()

def update_style(speaker_name):
    global now_style, speakers
    now_style = {}
    for i in speakers[speaker_name].styles:
        now_style[i.name] = i

    return gr.Dropdown.update(choices=[i for i in now_style.keys()], value=None)


async def get_voice_bytes(speaker_id: int, text: str, interrogative_speak: bool):
    async with Client() as client:
        return await (await client.create_audio_query(text, speaker_id)).synthesis(speaker=speaker_id, enable_interrogative_upspeak=interrogative_speak)


def ui():
    with gr.Accordion("Setting", open=True):
        # Gradio elements
        with gr.Row():
            activate = gr.Checkbox(value=params['activate'], label='Activate TTS', interactive=len(speakers) != 0,
                                   info="If extension can't connect to voicevox engine, it will be disable.")
            autoplay = gr.Checkbox(value=params['autoplay'], label='Play TTS automatically')
            translate = gr.Checkbox(value=params['translate'], label='Translate model output into Japanese for voicevox')

        with gr.Row():
            voice = gr.Dropdown(value=params['selected_voice'], choices=[i for i in speakers.keys()], label='TTS Voice')
            style = gr.Dropdown(value=params['selected_style'], choices=[], label='Voice style')
            interrogative_speak = gr.Checkbox(value=params['interrogative_speak'], label='interrogative speak')
        with gr.Row():
            engine = gr.Textbox(value=params['url'], label='voicevox engine url')
            refresh_connect = gr.Button(value='Refresh')

    # Event functions to update the parameters in the backend
    activate.change(lambda x: params.update({'activate': x}), activate, None)
    voice.change(lambda x: params.update({'selected_voice': x, 'selected_style': None, 'speaker_id': None}), voice, None).then(update_style, voice, style)
    autoplay.change(lambda x: params.update({"autoplay": x}), autoplay, None)
    style.change(lambda x: params.update({'selected_style': x, 'speaker_id': now_style[x].id if not (x is None) else None}), style, None)
    interrogative_speak.change(lambda  x: params.update({'interrogative_speak': x}), interrogative_speak, None)
    translate.change(lambda x: params.update({'translate': x}), translate, None)
    refresh_connect.click(lambda x: params.update({'url': x}), engine, None).then(connect, None, [voice, style, activate])

def output_modifier(string, state):
    global params, wav_idx

    if not params['activate'] or params['speaker_id'] is None:
        print(string)
        return string

    original_string = string
    string = remove_surrounded_chars(string)
    string = string.replace('"', '')
    string = string.replace('“', '')
    string = string.replace('\n', ' ')
    string = string.strip()
    if string == '':
        string = 'empty reply, try regenerating'

    output_file = Path(f'extensions/voicevox_tts/outputs/{wav_idx:06d}.mp3')
    print(f'Outputting audio to {str(output_file)}')
    if params['translate']:
        string = GoogleTranslator(target='ja').translate(string)
    audio = anyio.run(get_voice_bytes, params['speaker_id'], string, params['interrogative_speak'])
    with open(str(output_file), 'wb') as f:
        f.write(audio)

    autoplay = 'autoplay' if params['autoplay'] else ''
    string = f'<audio src="file/{output_file.as_posix()}" controls {autoplay}></audio>'
    wav_idx += 1

    string += f'\n\n{original_string}'

    shared.processing_message = "*Is typing...*"
    return string