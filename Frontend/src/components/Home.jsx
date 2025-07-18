import React from 'react';
import './../style/Home.css';

const Home = () => {
  return (
    <section 
      id="home"
      className="pt-28 lg:pt-36">
      <div className='container lg:grid lg:grid-cols-2 lg:gap-10'>
        <div className='flex flex-col justify-center gap-5 lg:gap-8'>
          <div className='flex items-center gap-3'> 
            <figure className='img-box'>
              <img src='src/images/me.jpeg' width={40} height={40} alt='DJI' className='img-cover' />
            </figure>
                        
            <div className='flex items-center gap-1-5 text-zinc-400 text-sm tracking-wide'>
              <span className='relative w-2 h-2 rounded-full bg-green-500'>
                <span className='absolute inset-0 rounded-full bg-green-500 animate-ping'></span>
              </span> 
              Available for work
            </div>
          </div>
          <h2 className='headline-1 max-w-15ch sm-max-w-20ch lg:max-w-[15ch] mt-5 mb-8 lg:mb-10'>
          Artificial Intelligence in Drones <br/>
          The Future of Smart Aerial Assistance
          </h2> 
          <div className='flex items-center gap-3'>
   
          </div>
        </div>
              
        <div className=''> 
          <figure className='w-full rounded-60px overflow-hidden shadow-lg'>
            <img src='src/images/dji-image.jpg' width={656} height={800} alt='DJI' className='w-full' />
          </figure>   
        </div>
      </div>          
    </section>
  );
};

export default Home;