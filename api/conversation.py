"""
Refactored ConversationHandler into its own file for aesthetic purposes, also not so messy to clutter up the main codebase.
IMPT: For any subsequent Handlers/functions, please import run_in_threadpool_decorator and wrap it around your I/O blocking functions.
Eg.

@run_in_threadpool_decorator("blocking_function")
def function_that_blocks(some_input) -> None:
    # Some synchronous code
    return 0

async nonblocking_func() -> None:
    await function_that_blocks(some_input) # Spins up the function in a separate thread.
"""
import openai
import logging
from dotenv import dotenv_values
import json
import random
from huggingface_hub import InferenceClient
from .utils import run_in_threadpool_decorator

from telegram import ForceReply, Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram import __version__ as TG_VER
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )

# get config 
config = dotenv_values(".env")

# get API tokens
HF_TOKEN = config['HF_API_KEY']
openai.api_key = config['OPENAI_API_KEY']

# assign variable name for each integer in sequence for easy tracking of conversation
(RESET_CHAT, 
 VALIDATE_USER, 
 USER_COMPANY, 
 EDIT_COMPANY, 
 IMAGE_TYPE, 
 IMAGE_PURPOSE, 
 SELECT_THEME, 
 SELECT_IMAGE_DESIGN,
 CUSTOM_IMAGE_PROMPT,
 GENERATE_PROMPT_AND_IMAGE, 
 GENERATE_IMAGE) = range(11)

# list of selected government agencies
lst_govt_agencies = ['Housing Development Board (HDB)',
                     'Government Technology Agency (GovTech)',
                     'Others']


# Enable logging
logging.basicConfig(
                    format="%(asctime)s - %(processName)s - %(threadName)s - [%(thread)d] - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
                    )
logger = logging.getLogger(__name__)
huggingFaceLogger = logging.getLogger("huggingface_hub").setLevel(logging.DEBUG)
messageHandlerLogger = logging.getLogger("telegram.bot").setLevel(logging.DEBUG)
applicationLogger = logging.getLogger("telegram.ext").setLevel(logging.DEBUG)



# define helper function to get model's response (using "gpt-3.5-turbo")
@run_in_threadpool_decorator("gpt_threads")
def get_completion(prompt:str, model: str, temperature: float) -> str:
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature, # this is the degree of randomness of the model's output
    )
    return response.choices[0].message["content"]

# define helper function to generate image
@run_in_threadpool_decorator("hugging_face_threads")
def txt2img(txt: str, image_path: str) -> None:
    client = InferenceClient(token=HF_TOKEN)
    image = client.text_to_image(prompt = txt, guidance_scale = random.uniform(6,9))
    image.save(image_path)
    return 0


# function for /start command (CommandHandler type)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message when the command /start is sent. 
    
    New users: username, chat ID, user's company are cached, then proceed to USER_COMPANY state
    Returning users: immediately proceed VALIDATE_USER state
    '''
    # get user
    user = update.effective_user

    # get username
    username = update.message.chat.username
    
    # get Chat ID
    chat_id = update.effective_chat.id
    
    # check if it is a new user: will need to initialise cache for user
    if not context.user_data:

        # initialise cache for user
        context.user_data['image_info'] = {'image_type': None,
                                           'image_purpose': None,
                                            'theme_output_json': None,
                                            'image_design_output_json': None,
                                            'user_selected_theme': None,
                                            'user_selected_image_design': None
                                            }
        
        # store username
        context.user_data['username'] = username
        
    # remove 'assistance_type' and 'state_for_assistance_type' keys for returning users
    if 'assistance_type' in context.user_data.keys():
        del context.user_data['assistance_type']
    
    if 'state_for_assistance_type' in context.user_data.keys():
        del context.user_data['state_for_assistance_type']
        
    # store chat ID
    context.user_data['chat_id'] = chat_id
    
    # get list of assistance types as options for buttons
    buttons_lst = [['Generate Image: Step-by-step Process'], ['Generate Image: Use Custom Prompt'], ['Edit Existing Image']]
    
    # output keyboard markup for user to respond
    await update.message.reply_html(
                                    f'Hi {user.mention_html()} \U0001F44B, I am Wo Ai AI Chatbot and I can generate posters, photographs, and illustrations.\n\nHow may I help you today?\nSelect an option below.',
                                    reply_markup = ReplyKeyboardMarkup(buttons_lst),
                                    )
    
    # check if user's company is cached
    if 'company' not in context.user_data.keys():
        return USER_COMPANY
    
    return VALIDATE_USER


# function to validate user's context before pointing to the required state
async def validate_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Validates user's information and then points user to the state based on selected assistance.
    '''
    # state entered from GENERATE_IMAGE/ GENERATE_PROMPT_AND_IMAGE states
    if 'Generate New Image' in update.message.text:
        
        # store assistance type
        context.user_data['assistance_type'] = 'Generate Image: Step-by-step Process'
        
        # store specific state for assistance type
        context.user_data['state_for_assistance_type'] = IMAGE_TYPE
        
    # state entered from /start (step-by-step process)
    elif 'assistance_type' not in context.user_data.keys() and 'company' in context.user_data.keys():
        
        # get user's assistance type
        assistance_type = update.message.text
        
        # store assistance type
        context.user_data['assistance_type'] = assistance_type

        # store state
        context.user_data['state_for_assistance_type'] = IMAGE_TYPE
    
    # 'Edit Existing Image' option selected    
    elif 'Edit Existing Image' in update.message.text:
        # get user's assistance type
        assistance_type = update.message.text
        
        # store assistance type
        context.user_data['assistance_type'] = assistance_type
        
        # store state for ending conversation
        context.user_data['state_for_assistance_type'] = ConversationHandler.END
        
    # get user to validate his information
    if 'Generate Image' in context.user_data['assistance_type']:
                
        # get user's company
        company = context.user_data['company']

        await update.message.reply_html(
                                        f'You are currently representing <strong>{company}</strong>.\n\nThis will influence the image generation process. To edit the company that you represent, click on "Edit Company Name". Otherwise, click on "Continue".',
                                        reply_markup = ReplyKeyboardMarkup([['Continue'], ['Edit Company Name']]),
                                        )
    elif 'Edit Existing Image' in context.user_data['assistance_type']:
        # delete user's company if it exists
        if 'company' in context.user_data.keys():
            del context.user_data['company']
            
        await update.message.reply_html(
                                        f'To edit an existing image, send one of the commands below:\n\n/inpainting - Replace/remove any object from an image\n/outpainting - Extend an image outwards\n\nSend /start for a new conversation.',
                                        reply_markup = ReplyKeyboardRemove(),
                                        )
    return context.user_data['state_for_assistance_type']


# function to get user's company info (MessageHandler type)
async def get_user_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Updates (returning user) or creates (new user) context.user_data['company']
    
    Users may enter this state from the various states: /start, /editcompany
    '''
    # entering from /start state (step-by-step process)
    if 'Generate Image' in update.message.text:
        # get user's assistance type
        assistance_type = update.message.text
        
        # store assistance type
        context.user_data['assistance_type'] = assistance_type
        
        # store specific state of selected assistance type for user
        context.user_data['state_for_assistance_type'] = IMAGE_TYPE
            
    # entering from get_user_company state
    elif 'state_for_assistance_type' in context.user_data.keys():
        # store user's company input
        context.user_data['company'] = update.message.text
    
    # check if it is a new user OR entering from /editcompany state
    if ('company' not in context.user_data.keys() and 'Step-by-step Process' in update.message.text) or 'edited_company' in context.user_data.keys():
        
        # remove 'edited_company' if present to reset condition
        if 'edited_company' in context.user_data.keys():
            del context.user_data['edited_company']
            
        # get list of govt agency buttons
        buttons_lst = [[agency_name] for agency_name in lst_govt_agencies]
        
        # output keyboard markup for user to respond to
        await update.message.reply_text(
                                        f'Which company are you generating this image for?\nSelect an option below.',
                                        reply_markup = ReplyKeyboardMarkup(buttons_lst),
                                        )
        return USER_COMPANY
    
    # check if 'Others' is selected
    elif context.user_data['company'] == 'Others':
        await update.message.reply_text(
                                        f'You have selected "Others".\n\nPlease type out the company you are representing.',
                                        reply_markup = ForceReply(selective = True)
                                        )
        return USER_COMPANY
    
    # if user's company is cached, proceed to validate user's input
    else:
        # get user's company
        company = context.user_data['company']
        
        # get user to validate his information
        await update.message.reply_html(
                                        f'You are currently representing <strong>{company}</strong>.\n\nThis will influence the image generation. To edit your company representation, click on "Edit Company Name". Otherwise, click on "Continue".',
                                        reply_markup = ReplyKeyboardMarkup([['Continue'], ['Edit Company Name']]),
                                        )
        
        return context.user_data['state_for_assistance_type']
    


# function to edit user's company (CommandHandler Type)
async def edit_company_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to user to edit company
    '''
    # store user's action of editing company
    context.user_data['edited_company'] = True
    
    # check if user's company is cached
    if 'company' in context.user_data.keys():
        
        # get user's company
        company = context.user_data['company']
        
        # ask user to edit company input or not
        await update.message.reply_html(
                                        f'Your current company is <strong>{company}</strong>.\n\nWould you like to change it?\nSelect an option below.',
                                        reply_markup = ReplyKeyboardMarkup([['Yes'], ['No']]),
                                        )
        # proceed to state that handles user's company input
        return USER_COMPANY
    else:
        # ask user to restart the conversation as there is no company name to edit
        await update.message.reply_html(
                                        f'There is no company name to edit. Please send /start for a new conversation.',
                                        )

        # remove 'edited_company' key
        del context.user_data['edited_company']
        
        # proceed specified state to get user's company
        return RESET_CHAT
    
# function to get user's input on the type of image (MessageHandler type)
async def get_image_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to ask for image type
    '''
    # get user
    user = update.effective_user
    
    # get list of image options for buttons
    buttons_lst = [['Poster'], ['Realistic Photo'], ['Illustration']]
    
    # output keyboard markup for user to respond to
    await update.message.reply_html(
                                    f'What type of image would you like to create?\nSelect an option below.',
                                    reply_markup = ReplyKeyboardMarkup(buttons_lst),
                                    )   
    return IMAGE_PURPOSE

# function to get user's input on the purpose of image (MessageHandler type)
async def get_image_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to ask for purpose of image type
    '''
    # get previous input of user
    text = update.message.text

    # store users' input
    context.user_data['image_info']['image_type'] = text.lower()

    # ask for purpose of image
    await update.message.reply_text(
                                    f'Type out the purpose of the {text.lower()}:\n(Examples: New housing estate in Bedok, Data science for public good)',
                                    reply_markup = ForceReply(selective = True)
                                    )           
    return SELECT_THEME

# function to select theme based on purpose of image (MessageHandler type)
async def get_theme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Prompts chatgpt to generate themes and sends a message to ask user 
    to select one of the themes generated by chatgpt.
    '''    
    # helper function to get theme prompt with template
    def get_prompt(company, image_type, user_input):
        # prompt template for chatgpt to generate themes
        prompt = f'''
        You are a digital marketing AI assistant for {company} in Singapore. 
        Suggest 5 {image_type} themes for the following description: {user_input} in less than 20 words for each theme.
        Use '\'s' for any word that requires ```'s```, example: the house\'s window.
        Return the result in a JSON format, example:''' +\
        r'''
        {
            1: result,
            2: result2,
            3: result3
        }'''
        
        return prompt

    # inform user to wait
    await update.message.reply_html(
                                    f'''\U0001F538 <strong>Loading proposed themes based on purpose</strong> \U0001F538''',
                                    reply_markup = ReplyKeyboardRemove(),
                                    ) 
    
    # get user's company
    company = context.user_data['company']
    
    # get user's selectedimage type
    image_type = context.user_data['image_info']['image_type']
    
    # check if user requested to regenerate themes
    if update.message.text == 'Propose other themes':
        
        # get user's image purpose
        user_input = context.user_data['image_info']['image_purpose']
        
        # get prompt
        prompt = get_prompt(company, image_type, user_input)
        
        # get chatgpt's response (random temperature value between 0.1 to 0.6)
        response = await get_completion(prompt,"gpt-3.5-turbo" , random.uniform(0.1, 0.6))
        themes = eval(response)
        
    else:
        # get user input (purpose of image)
        user_input = update.message.text
        
        # store user's image purpose
        context.user_data['image_info']['image_purpose'] = user_input
        
        # get prompt
        prompt = get_prompt(company, image_type, user_input)
        
        # get chatgpt's response
        response = await get_completion(prompt, "gpt-3.5-turbo", 0)
        themes = eval(response)

    # store results
    context.user_data['theme_output_json'] = themes
    
    # process output text
    lst_themes = list(themes.values())
    buttons_lst = []
    output_text = 'Here are 5 proposed themes based on your input:\nSelect an option below.\n\n'
    for theme_index in range(len(lst_themes)):
        # get theme
        theme = lst_themes[theme_index]
        
        # indicate option number for theme
        option = f'Theme {theme_index+1}'
        
        # append text
        output_text += '<strong>' + option + '</strong>' + '\n'
        output_text += theme + '\n\n'
        
        # append option text value for buttons in KeyboardMarkup format
        buttons_lst.append([option])
    
    # add additonal buttons
    buttons_lst.extend([['Propose other themes'], ['Write own theme']])
    
    # ask user to select one of the proposed themes
    await update.message.reply_html(
                                    f'{output_text}',
                                    reply_markup = ReplyKeyboardMarkup(buttons_lst, resize_keyboard = True),
                                    )      

    return SELECT_IMAGE_DESIGN

# function to get user's custom theme input
async def get_user_custom_theme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to request for user's custom theme
    '''
    # Request for custom image design
    await update.message.reply_html(
                                    f'''
                                    Please type out your custom theme.\n\nSend /choosetheme to select any of the previously suggested image designs.
                                    ''',
                                    reply_markup = ForceReply(selective = True),
                                    )  

    
    # check if user's company is set
    if 'company' not in context.user_data.keys():
        
        # cache user's state for assistance type
        context.user_data['state_for_assistance_type'] = SELECT_IMAGE_DESIGN
        
        # proceed to specified state to get user's company detail
        return USER_COMPANY
    
    return SELECT_IMAGE_DESIGN

# function to select previously suggested image designs
async def get_previous_themes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to request for user to select an image design
    '''
    if 'theme_output_json' not in context.user_data.keys() or context.user_data['theme_output_json'] == None:
        # ask user to restart the conversation as there is no company name to edit
        await update.message.reply_html(
                                        f'There is no theme to select. Please send /start for a new conversation.',
                                        )
        return RESET_CHAT
    
    # get suggested themes dictionary
    themes = context.user_data['theme_output_json']
    
    # process output text
    lst_themes = list(themes.values())
    buttons_lst = []
    output_text = 'Here are 5 proposed themes based on your input:\nSelect an option below.\n\n'
    for theme_index in range(len(lst_themes)):
        # get theme
        theme = lst_themes[theme_index]
        
        # indicate option number for theme
        option = f'Theme {theme_index+1}'
        
        # append text
        output_text += '<strong>' + option + '</strong>' + '\n'
        output_text += theme + '\n\n'
        
        # append option text value for buttons in KeyboardMarkup format
        buttons_lst.append([option])
    
    # add additonal buttons
    buttons_lst.extend([['Propose other themes'], ['Write own theme']])
    
    # ask user to select one of the proposed themes
    await update.message.reply_html(
                                    f'{output_text}',
                                    reply_markup = ReplyKeyboardMarkup(buttons_lst, resize_keyboard = True),
                                    )      

    return SELECT_IMAGE_DESIGN
    
# function to select image design based on selected theme
async def select_image_design(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Prompts ChatGPT to generate image designs and sends a message to ask user 
    to select one of the generated image designs.
    '''
    # helper function to get image design prompt with template
    def get_prompt(company, selected_theme, image_type):
        # specify design attributes format for chatgpt
        design_attributes = {
            'image description': 'none',
            'style of visual image': 'none',
            'object in foreground description': 'none'
        }
        
        # write the prompt to chatgpt
        prompt = r'''
        You are a digital marketing AI assistant for '''+ company + r''' in Singapore. 
        Given the theme of a '''+ image_type + r''' delimited by ```, suggest 5 different outputs to replace "none" 
        for the specified design attributes provided in a JSON format delimited by ```.
        Keep in mind that the outputs must either be modern, futuristic, minimalistic, or stylish.
        Use '\'s' for any word that requires ```'s```, example: the house\'s window.

        Return the output in a JSON format, example:
        {'output_1': {
            'image description': "none",
            'style of visual image': "none",
            'object in foreground description': "none",
            },
        'output_2': {'image description': "none",
            'style of visual image': "none",
            'object in foreground description': "none",
            },
        'output_3': {'image description': "none",
            'style of visual image': "none",
            'object in foreground description': "none",
            }
        }''' + f'''
        theme: {selected_theme}
        design attributes: {design_attributes}'''
        
        return prompt
    
    # inform user to wait
    await update.message.reply_html(
                                    f'''\U0001F538 <strong>Loading proposed image designs</strong> \U0001F538''',
                                    reply_markup = ReplyKeyboardRemove(),
                                    ) 
    
    # get user's company
    company = context.user_data['company']
    
    # check if user requested for regeneration of image designs
    if update.message.text == 'Propose other image designs':
        # get selected theme
        selected_theme = context.user_data['image_info']['user_selected_theme']
        
        # get image type
        image_type = context.user_data['image_info']['image_type']
        
        # get prompt for chatgpt
        prompt = get_prompt(company, selected_theme, image_type)
        
        # get chatgpt's response (increased temperature from 0.1 to 0.6)
        response = await get_completion(prompt, "gpt-3.5-turbo", random.uniform(0.1, 0.6))
        image_designs_dict = eval(response)
    
    # new user's image designs generation
    else: 
        # check if user input custom theme
        if not any(theme_option in update.message.text for theme_option in ['Theme 1', 'Theme 2', 'Theme 3', 'Theme 4', 'Theme 5']):
            # store user's custom theme
            selected_theme = update.message.text
            context.user_data['image_info']['user_selected_theme'] = selected_theme

        else:
            # get user input (selection for theme of image)
            user_input = update.message.text
            
            # get selected theme
            selected_option_number = int(user_input[-1])
            selected_theme = context.user_data['theme_output_json'][selected_option_number]
            
            # store user's selected theme
            context.user_data['image_info']['user_selected_theme'] = selected_theme
        
        # get image type
        image_type = context.user_data['image_info']['image_type']
        
        # get prompt for chatgpt
        prompt = get_prompt(company, selected_theme, image_type)
        
        # get chatgpt's response
        response = await get_completion(prompt, "gpt-3.5-turbo", 0)
        image_designs_dict = eval(response)
        
    # store image designs output
    context.user_data['image_info']['image_design_output_json'] = image_designs_dict

    # get list of suggested image descriptions
    output_text = f''
    for output_id, output in image_designs_dict.items():
        # append output ID to string output
        output_text += f'<strong>Image Design {output_id[-1]}</strong>\n'
        
        # get each output description
        image_description = output['image description']
        foreground_object = output['object in foreground description']
        image_style = output['style of visual image']
        
        # append each output description to string output
        image_design_text = f'\u25AA Image description: <i>{image_description}</i>' + f'\n\u25AA Object in foreground: <i>{foreground_object}</i>' + f'\n\u25AA Style of image: <i>{image_style}</i>\n\n'
        output_text += image_design_text
        
    # get list of suggested image design in KeyboardMarkup format
    buttons_lst = [[f'Image Design {val}'] for val in range(1, len(image_designs_dict)+1)]
    buttons_lst.extend([['Propose other image designs'], ['Write own image design']])
    
    # ask user to select any of the options available
    await update.message.reply_html(
                                    f'''
                                    Here are 5 proposed image designs based on your input:\nSelect an option below.\n\n{output_text}
                                    ''',
                                    reply_markup = ReplyKeyboardMarkup(buttons_lst, resize_keyboard = True),
                                    )      
    
    return GENERATE_PROMPT_AND_IMAGE

# function to get user's custom image design
async def get_user_custom_image_design(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to request for user's custom image design
    '''
    # Request for custom image design
    await update.message.reply_html(
                                    f'''
                                    Please type out your custom image design, add "/" after each design element. Use this format:\n\n<i>Image Description</i> / <i>Object in foreground</i> / <i>Style of image</i>\ne.g. A polaroid photo of Space Shuttle Discovery launch / crew waving from the cockpit / vintage\n\nSend /choosedesign to select any of the previously suggested image designs.
                                    ''',
                                    reply_markup = ForceReply(selective = True),
                                    )  
    
    # image type will be set to 'image' by default since user can input own image description
    context.user_data['image_info']['image_type'] = 'image'
    
    # remove 'image_prompt' key if it exists
    if 'image_prompt' not in context.user_data.keys():
        del context.user_data['image_prompt']
        
    # check if user's company is set
    if 'company' not in context.user_data.keys():
        
        # cache user's state for assistance type
        context.user_data['state_for_assistance_type'] = IMAGE_TYPE
        
        # proceed to specified state to get user's company detail
        return USER_COMPANY
    
    return GENERATE_PROMPT_AND_IMAGE

# function to select previously suggested image designs
async def get_previous_image_designs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Sends a message to request for user to select an image design
    '''
    if context.user_data['image_info']['image_design_output_json'] == None:
        # ask user to restart the conversation as there is no company name to edit
        await update.message.reply_html(
                                        f'There is no image design to select. Please send /start for a new conversation.',
                                        )
        return RESET_CHAT
    
    # get suggested image descriptions dictionary
    image_designs_dict = context.user_data['image_info']['image_design_output_json']
    
    # get list of suggested image descriptions
    output_text = ''
    for output_id, output in image_designs_dict.items():
        # append output ID to string output
        output_text += f'<strong>Image Design {output_id[-1]}</strong>\n'
        
        # get each output description
        image_description = output['image description']
        foreground_object = output['object in foreground description']
        image_style = output['style of visual image']
        
        # append each output description to string output
        image_design_text = f'\u25AA Image description: <i>{image_description}</i>' + f'\n\u25AA Object in foreground: <i>{foreground_object}</i>' + f'\n\u25AA Style of image: <i>{image_style}</i>\n\n'
        output_text += image_design_text
        
    # get list of suggested image design in KeyboardMarkup format
    buttons_lst = [[f'Image Design {val}'] for val in range(1, len(image_designs_dict)+1)]
    context.user_data['image_info']['image_design_output_json'] = image_designs_dict
    buttons_lst.extend([['Propose other image designs'], ['Write own image design']])
    
    # ask user to select any of the options available
    await update.message.reply_html(
                                    f'''
                                    Here are 5 proposed image designs based on your input:\nSelect an option below.\n\n{output_text}
                                    ''',
                                    reply_markup = ReplyKeyboardMarkup(buttons_lst, resize_keyboard = True),
                                    ) 
    return GENERATE_PROMPT_AND_IMAGE

# function to requests user's text-to-image prompt
async def get_user_custom_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Requests for user's custom text-to-image prompt
    '''
    # store state
    context.user_data['state_for_assistance_type'] = CUSTOM_IMAGE_PROMPT
    
    await update.message.reply_text(
                                    f'''
                                    Please type out your text-to-image prompt below.
                                    ''',
                                    reply_markup = ForceReply(selective = True),
                                    )
    
    # delete 'image_prompt' key if it exists
    if 'image_prompt' in context.user_data['image_info']:
        del context.user_data['image_info']['image_prompt']
    
    # set value of 'image_type' to 'image'
    context.user_data['image_info']['image_type'] = 'image'

    return GENERATE_IMAGE

# function to generate text-to-image prompt and image
async def generate_prompt_and_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    '''
    Generate text-to-image prompt and its image
    '''
    '''
    Generate text-to-image prompt based on selected image design
    '''
    # get user's company
    company = context.user_data['company']
    
    # check if entering from custom design state
    if '/' in update.message.text or not any(output_text in update.message.text for output_text in ['Image Design 1', 'Image Design 2', 'Image Design 3', 'Image Design 4', 'Image Design 5', 'Propose other image designs', 'Write own image design']):
        
        # get list of elements
        design_elements_lst = update.message.text.split('/')
        
        # repeat custom image input if format is wrong
        if len(design_elements_lst)!=3:
            # Request for custom image design
            await update.message.reply_html(
                                            f'''
                                            Incorrect format passed.\n\nPlease type out your custom image design, add "/" after each design element. Use this format:\n\n<i>Image Description</i> / <i>Object in foreground</i> / <i>Style of image</i>\ne.g. A polaroid photo of Space Shuttle Discovery launch / crew waving from the cockpit / vintage\n\nSend /choosedesign to select any of the previously suggested image designs.
                                            ''',
                                            reply_markup = ForceReply(selective = True),
                                            )  
            return GENERATE_PROMPT_AND_IMAGE
        
        selected_image_design_dict = {'image description': design_elements_lst[0],
                                      'object in foreground description': design_elements_lst[1],
                                      'style of visual image': design_elements_lst[2]}
    
    else:
        # get user input (selection for theme of image)
        user_input = update.message.text
        
        # get cached result for selected image design
        selected_output_id = f'output_{user_input[-1]}'
        
        # select image design dictionary based on user's selection
        for output_id, image_design_dict in context.user_data['image_info']['image_design_output_json'].items():
            if output_id == selected_output_id:
                selected_image_design_dict = image_design_dict
                
                # store user's selected image design
                context.user_data['image_info']['user_selected_image_design'] = selected_image_design_dict
                break
    
    # get cached result for selected image type
    image_type = context.user_data['image_info']['image_type']
    
    # initialise variables for gpt prompt
    style_image = selected_image_design_dict['style of visual image']
    object_for_image = selected_image_design_dict['object in foreground description']
    image_description = selected_image_design_dict['image description']
    image_style = selected_image_design_dict['style of visual image']
    
    # check if custom image design is used: image_type will be set to 'image'
    if image_type == 'image':
        design_attributes = {
        'colour palette': f'{style_image}',
        'type of image': f'{image_type}',
        'foreground of image': f'{image_description}',
        'props used in image': f'{object_for_image}',
        'style of image': f'{image_style}',
        'resolution': '8k'
        }
    else:
        design_attributes = {
            'colour palette': f'{style_image}',
            'foreground of image': f'{image_description}',
            'props used in image': f'{object_for_image}',
            'style of image': f'{image_style}',
            'resolution': '8k'
        }

    sample_prompts = ['A still life of flowers, in the style of Jan van Huysum’s paintings, with a lush arrangement of blooms in a vase, surrounded by delicate butterflies, bees, and other insects.',
                    'A digital collage of iconic tech gadgets, such as the iPhone, MacBook, and Amazon Echo, in the style of David Hockney.',
                    'A surreal underwater world in the style of Salvador Dali, where all the sea creatures are actually different tech gadgets like iPhones, laptops, and smartwatches, floating amongst the seaweed and coral.',
                    'A space station in the style of Stanley Kubrick’s 2001: A Space Odyssey, where all the spaceships and equipment are made of different popular candy bars like Snickers, Milky Way, and Three Musketeers, and all the astronauts are dressed as characters from Star Trek.',
                    'A retro pop art-style illustration of the famous Hollywood sign, surrounded by colorful and iconic classic cars like the Corvette and the Mustang.',
                    'A surreal, abstract landscape, inspired by Joan Miró’s paintings, with strange shapes, lines, and colors arranged in an imaginary world, with floating objects like planets and stars.',
                    'main model shoot style, 8k 3d render sharp focus photography low angle shot high detail, beautiful Chinese fantasy woman portrait, teenage 23 years old, Looking at camera, fierce gaze, black lace textures, Michael parkes art, fantasy concept, 1379 Chiba imperial dynasty concubine. mythology, sleeveless gothic black gown, holding a dragon, red lips stained dripping honey, floral flower organic textures. realistic object octane Renders, outdoor lowlight moonlight dark dirty forest, dynamic lighting full length portrait, octane volumetric lighting, edge lighting, octane render, 8k, perfect shading, trending on artstation, ultra-realistic, concept art, Dark Mode, Tones of Black in Background, Spotlight, Beautiful cinematic shot + photos taken by ARRI, photos taken by sony, photos taken by canon, photos taken by nikon, photos taken by sony, photos taken by hasselblad + incredibly detailed, sharpen, details + professional lighting, photography lighting + 50mm, 80mm, 100m + lightroom gallery + behance photographys + unsplash –ar 2:3'
                    'The Battle of Agincourt, 1415 - A bird’s eye view of the Battle of Agincourt, with English and French soldiers clashing on the battlefield and arrows raining down from the sky. In the style of Peter Paul Rubens’ Baroque battle scenes.',
                    'A steampunk-inspired train station, where all the trains are made of different popular soda brands like Coca-Cola, Pepsi, and Dr. Pepper, and the passengers are robots and cyborgs.',
                    'A spooky graveyard in the style of Edward Gorey, where all the tombstones and monuments are made of different popular cookies like Oreos, Chips Ahoy, and Nutter Butters, and all the ghosts are dressed as characters from The Addams Family.',
                    'Create a photojournalistic-style image of Winston Smith as he starts to rebel against the oppressive government in George Orwell’s “1984.” Show him standing in front of a “Big Brother” poster, with a determined look on his face and the cityscape of Airstrip One in the background.',
                    'Using a minimalist, sketch-like style, create an image of Holden Caulfield sitting on a bench in Central Park, New York, deep in thought as he contemplates the world around him. Show his melancholic expression and the cityscape behind him, with a backdrop of the wintry New York sky.',
                    'Using a whimsical, fantasy-style illustration, create an image of Alice in Wonderland falling down the rabbit hole. Show her surrounded by fantastical creatures, with the White Rabbit peeking out from behind a tree and a sense of wonder and adventure in the air.'
                    ]

    prompt = r'''
    You are a digital marketing AI assistant for '''+ company + r''' in Singapore. 
    Your task is to describe the image based on specified design attributes such as type, description 
    and styling of image which will be given in a JSON format.
    Follow the description structure of the list of sample image descriptions provided which are delimited by ```.
    Then, given the design attributes delimited by ``` , 
    describe the image as a prompt in a JSON format: {'prompt': generated_output}
    where the generated output will replace the space of 'generated_output'.
    Use '\'s' for any word that requires ```'s```, example: the house\'s window.
    
    To describe the image, do the following:
    - first, describe the image given the design attributes
    - second, compare your description with the sample image descriptions provided and 
    verify if your description structure is similar to the samples
    - lastly, if your image description is not similar, provide another image description given the design attributes, 
    following the description structure of the samples

    Use the following format:
    {'Your image description': image description here,
    'Is the sentence structure of your image description similar to the sample image descriptions': 'Yes or No',
    'Your final image description': final image description that has a similar sentence structure to the sample image descriptions,
    'prompt': final image description
    }
    ''' +\
    f'''
    design attributes: ```{design_attributes}```
    sample image descriptions: ```{sample_prompts}```
    '''
    await update.message.reply_html(
                                    f'''\U0001F538 <strong>Generating {image_type}</strong> \U0001F538\n(Please wait for up to 5 mins \U0001F557)''',
                                    reply_markup = ReplyKeyboardRemove(),
                                    )
    # get chatgpt's response
    response = await get_completion(prompt, "gpt-3.5-turbo", 0)
    image_prompt = eval(response)['prompt']
    
    # cache generated prompt
    context.user_data['image_info']['image_prompt'] = image_prompt
    
    # get username
    username = context.user_data['username']
    
    client = InferenceClient(token=HF_TOKEN)
    update_as_dict = update.to_dict()
    update_as_json = json.dumps(update_as_dict)
    logger.info(update_as_json)
    logger.info(update_as_dict["message"]["from"]["first_name"]+ " "+ "sent the message of:" + update.message.text)
    
    # spin up another thread to await completion of huggingface API
    image_path = f"data/image_output/{username}_output.png"
    await txt2img(image_prompt, image_path)
    
    
    # Send image prompt to user 
    await update.message.reply_html(
                                    f'''<strong>Text-to-Image Prompt used:</strong>\n{image_prompt}''',
                                    )
    
    # send image to user
    await context.bot.send_photo(
        chat_id = context.user_data['chat_id'],
        photo = open(image_path, "rb"),
        write_timeout = 150
    )
    
    # output text template
    lst_commands = ['/editcompany - edit your company name',
                    '/choosetheme - choose another previously proposed theme', 
                    '/choosedesign - choose another previously proposed image design',
                    '/start - start a new conversation',
                    '/quit - stop the conversation']
    output_text = f'Done! Your {image_type} has been generated. Can I help you with anything else?\nSelect an option below.\n\nYou can also control me by sending these commands:\n\n'
    for command_description in lst_commands:
        output_text += command_description + '\n'
    
    # send text to user
    await update.message.reply_text(
                                    f'{output_text}',
                                    reply_markup = ReplyKeyboardMarkup([['Generate Image Again'], ['Generate New Image: Step-by-step Process'], ['Generate New Image: Use Custom Prompt'], ['Edit Existing Image']]),
                                    )
    return RESET_CHAT


# function to generate and output image to user
async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Generate image based on generated or user's custom text-to-image prompt
    """
    # get username
    username = context.user_data['username']
    
    # get image type
    image_type = context.user_data['image_info']['image_type']
    
    # check if user input is custom image prompt
    if 'image_prompt' not in context.user_data['image_info'].keys():
        # get image prompt
        image_prompt = update.message.text
        
        # store image prompt
        context.user_data['image_info']['image_prompt'] = image_prompt
    
    # user request to regenerate image
    else:
        image_prompt = context.user_data['image_info']['image_prompt']
        
    client = InferenceClient(token=HF_TOKEN)
    update_as_dict = update.to_dict()
    update_as_json = json.dumps(update_as_dict)
    logger.info(update_as_json)
    logger.info(update_as_dict["message"]["from"]["first_name"]+ " "+ "sent the message of:" + update.message.text)
    
    await update.message.reply_html(
                                    f'''\U0001F538 <strong>Generating {image_type}</strong> \U0001F538\n(Please wait for up to 5 mins \U0001F557)''',
                                    reply_markup = ReplyKeyboardRemove(),
                                    )
    
    # spin up another thread to await completion of huggingface API
    image_path = f"data/image_output/{username}_output.png"
    await txt2img(image_prompt, image_path)
    
    # Send image prompt to user 
    await update.message.reply_html(
                                    f'''<strong>Text-to-Image Prompt used:</strong>\n{image_prompt}''',
                                    )
    
    # send image to user
    await context.bot.send_photo(
        chat_id = context.user_data['chat_id'],
        photo = open(image_path, "rb"),
        write_timeout = 150,
    )

    # output text template
    lst_commands = ['/editcompany - edit your company name',
                    '/choosetheme - choose another previously proposed theme', 
                    '/choosedesign - choose another previously proposed image design',
                    '/start - start a new conversation',
                    '/quit - stop the conversation']
    output_text = f'Done! Your {image_type} has been generated. Can I help you with anything else?\nSelect an option below.\n\nYou can also control me by sending these commands:\n\n'
    for command_description in lst_commands:
        output_text += command_description + '\n'
    await update.message.reply_text(
                                    f'{output_text}',
                                    reply_markup = ReplyKeyboardMarkup([['Generate Image Again'], ['Generate New Image: Step-by-step Process'], ['Generate New Image: Use Custom Prompt'], ['Edit Existing Image']]),
                                    )
    return RESET_CHAT

# function to quit and end conversation (CommandHandler type)
async def quit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Quits the conversation by stopping the bot.
    '''
    # get user
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    
    await update.message.reply_text(
        "Thank you and have a nice day.\n\nSend /start for a new conversation.", reply_markup=ReplyKeyboardRemove()
    )
    
    # delete user's cache
    for key in list(context.user_data.copy().keys()):
        del context.user_data[key]
        
    return ConversationHandler.END